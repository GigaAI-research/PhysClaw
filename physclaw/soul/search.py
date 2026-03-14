"""Memory index and hybrid search (TF-IDF + BM25).

Reference: OpenClaw src/memory/manager.ts
Reference: OpenClaw src/memory/internal.ts (MemoryChunk)
Reference: docs/concepts/memory.md "Hybrid search"

Search architecture:
  1. Chunk: split by markdown headings
  2. Vector search: TF-IDF cosine similarity (weight 0.7)
  3. Keyword search: BM25 ranking (weight 0.3)
  4. Hybrid: finalScore = 0.7 * vectorScore + 0.3 * textScore
  5. Defaults: maxResults=6, minScore=0.35, maxSnippetChars=700
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Hybrid search config (matching OpenClaw defaults)
SEARCH_MAX_RESULTS = 6
SEARCH_MIN_SCORE = 0.35
SEARCH_MAX_SNIPPET_CHARS = 700
HYBRID_VECTOR_WEIGHT = 0.7
HYBRID_TEXT_WEIGHT = 0.3


def _tokenize(text: str) -> list[str]:
    """Tokenize: lowercase + split on non-alphanumeric. Keep Chinese chars and 2+ char tokens."""
    return [t for t in re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower())
            if len(t) > 1 or "\u4e00" <= t <= "\u9fff"]


def _cosine_sim(a: dict[str, float], b: dict[str, float]) -> float:
    """Sparse vector cosine similarity."""
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freq: Counter,
    n_docs: int,
    k1: float = 1.2,
    b: float = 0.75,
    avgdl: float = 100.0,
) -> float:
    """Single document BM25 score (Okapi BM25)."""
    dl = len(doc_tokens)
    tf_doc = Counter(doc_tokens)
    score = 0.0
    for term in set(query_tokens):
        tf = tf_doc.get(term, 0)
        if tf == 0:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1)))
        score += idf * tf_norm
    return score


class MemoryIndexManager:
    """Agent memory index manager.

    Reference: OpenClaw MemoryIndexManager (src/memory/manager.ts)

    Directory structure (within agent workspace):
      MEMORY.md          Long-term memory (curated, optional)
      memory/
        2026-03-04.md    Daily append log
        2026-03-03.md
        ...
    """

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir
        self.memory_md = workspace_dir / "MEMORY.md"
        self.memory_dir = workspace_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # -- Write --

    def write_daily(self, content: str, category: str = "general") -> str:
        """Append to today's memory/YYYY-MM-DD.md."""
        today = date.today().isoformat()
        path = self.memory_dir / f"{today}.md"
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"\n## [{ts}] {category}\n\n{content}\n"

        if not path.exists():
            path.write_text(f"# Memory Log: {today}\n", encoding="utf-8")
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
        return f"memory/{today}.md"

    # -- Read --

    def read_file(
        self,
        rel_path: str,
        from_line: int | None = None,
        n_lines: int | None = None,
    ) -> dict:
        """Safe read of a memory file within workspace."""
        normalized = rel_path.replace("\\", "/")
        allowed = (
            normalized in ("MEMORY.md", "memory.md")
            or normalized.startswith("memory/")
        )
        if not allowed or ".." in normalized:
            return {"path": rel_path, "text": "", "error": "Access denied"}

        full = self.workspace_dir / normalized
        if not full.exists():
            return {"path": rel_path, "text": "", "error": f"Not found: {rel_path}"}
        if full.is_symlink():
            return {"path": rel_path, "text": "", "error": "Symlinks rejected"}

        try:
            text = full.read_text(encoding="utf-8")
        except Exception as e:
            return {"path": rel_path, "text": "", "error": str(e)}

        lines = text.split("\n")
        if from_line is not None:
            start = max(0, from_line - 1)
            end = (start + n_lines) if n_lines else len(lines)
            lines = lines[start:end]

        return {"path": rel_path, "text": "\n".join(lines), "totalLines": len(lines)}

    def load_evergreen(self) -> str:
        """Read MEMORY.md (long-term memory)."""
        for name in ("MEMORY.md", "memory.md"):
            p = self.workspace_dir / name
            if p.exists() and not p.is_symlink():
                try:
                    return p.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
        return ""

    def get_recent_daily(self, days: int = 3) -> list[dict]:
        """Get the most recent N days of daily logs."""
        results = []
        today = date.today()
        for i in range(days):
            d = today - timedelta(days=i)
            path = self.memory_dir / f"{d.isoformat()}.md"
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8").strip()
                    results.append({
                        "path": f"memory/{d.isoformat()}.md",
                        "date": d.isoformat(),
                        "content": content,
                    })
                except Exception:
                    pass
        return results

    # -- Index --

    def _collect_memory_files(self) -> list[Path]:
        """Collect all indexable .md files in workspace."""
        files: list[Path] = []
        for name in ("MEMORY.md", "memory.md"):
            p = self.workspace_dir / name
            if p.exists() and not p.is_symlink():
                files.append(p)
                break
        if self.memory_dir.exists():
            for md in sorted(self.memory_dir.glob("**/*.md"), reverse=True):
                if not md.is_symlink():
                    files.append(md)
        return files

    def _chunk_file(self, path: Path) -> list[dict]:
        """Split file into chunks by markdown headings."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return []

        rel = str(path.relative_to(self.workspace_dir))
        lines = content.split("\n")
        chunks: list[dict] = []
        buf: list[str] = []
        buf_start = 1

        for i, line in enumerate(lines):
            if line.startswith("#") and buf:
                text = "\n".join(buf).strip()
                if text:
                    chunks.append({
                        "path": rel, "text": text,
                        "startLine": buf_start,
                        "endLine": buf_start + len(buf) - 1,
                        "source": "memory",
                    })
                buf = [line]
                buf_start = i + 1
            else:
                buf.append(line)

        if buf:
            text = "\n".join(buf).strip()
            if text:
                chunks.append({
                    "path": rel, "text": text,
                    "startLine": buf_start,
                    "endLine": buf_start + len(buf) - 1,
                    "source": "memory",
                })
        return chunks

    def _build_index(self) -> list[dict]:
        """Build full chunk index."""
        chunks: list[dict] = []
        for f in self._collect_memory_files():
            chunks.extend(self._chunk_file(f))
        return chunks

    # -- Search --

    def search(
        self,
        query: str,
        *,
        max_results: int = SEARCH_MAX_RESULTS,
        min_score: float = SEARCH_MIN_SCORE,
    ) -> list[dict]:
        """Hybrid search: TF-IDF vector + BM25 keyword.

        Reference: OpenClaw src/memory/hybrid.ts mergeHybridResults()
        """
        chunks = self._build_index()
        if not chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        doc_freq: Counter = Counter()
        all_tokens: list[list[str]] = []
        total_len = 0

        for c in chunks:
            toks = _tokenize(c["text"])
            all_tokens.append(toks)
            for t in set(toks):
                doc_freq[t] += 1
            total_len += len(toks)

        n_docs = len(chunks)
        avgdl = total_len / max(n_docs, 1)

        # TF-IDF vector search
        def _idf(term: str) -> float:
            df = doc_freq.get(term, 0)
            return math.log(n_docs / df) if df else 0.0

        q_tf = Counter(query_tokens)
        q_vec = {t: (cnt / len(query_tokens)) * _idf(t) for t, cnt in q_tf.items()}

        vector_scores: list[float] = []
        for toks in all_tokens:
            if not toks:
                vector_scores.append(0.0)
                continue
            tf = Counter(toks)
            c_vec = {t: (cnt / len(toks)) * _idf(t) for t, cnt in tf.items()}
            vector_scores.append(_cosine_sim(q_vec, c_vec))

        # BM25 keyword search
        bm25_raw: list[float] = []
        for toks in all_tokens:
            bm25_raw.append(_bm25_score(query_tokens, toks, doc_freq, n_docs, avgdl=avgdl))

        max_bm25 = max(bm25_raw) if bm25_raw else 1.0
        text_scores = [(s / max_bm25 if max_bm25 > 0 else 0.0) for s in bm25_raw]

        # Hybrid merge
        results: list[dict] = []
        for i, chunk in enumerate(chunks):
            score = (HYBRID_VECTOR_WEIGHT * vector_scores[i]
                     + HYBRID_TEXT_WEIGHT * text_scores[i])
            if score < min_score:
                continue
            snippet = chunk["text"][:SEARCH_MAX_SNIPPET_CHARS]
            citation = (f"{chunk['path']}#L{chunk['startLine']}"
                        if chunk["startLine"] == chunk["endLine"]
                        else f"{chunk['path']}#L{chunk['startLine']}-L{chunk['endLine']}")
            results.append({
                "path": chunk["path"],
                "startLine": chunk["startLine"],
                "endLine": chunk["endLine"],
                "score": round(score, 4),
                "snippet": snippet,
                "source": chunk["source"],
                "citation": citation,
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:max_results]


# Global manager cache
_managers: dict[str, MemoryIndexManager] = {}


def get_memory_manager(agent: Any) -> MemoryIndexManager:
    """Get or create a MemoryIndexManager for an agent."""
    agent_id = agent.id if hasattr(agent, "id") else str(agent)
    workspace = getattr(agent, "workspace_dir", None)
    if agent_id not in _managers and workspace:
        _managers[agent_id] = MemoryIndexManager(workspace)
    return _managers[agent_id]
