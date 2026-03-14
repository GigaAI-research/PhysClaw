"""Session persistence store.

Two-layer storage:
  Layer 1: sessions.json  - Metadata index (keys, timestamps, message counts)
  Layer 2: transcripts/*.jsonl - Append-only per-session message logs

Reference: OpenClaw src/sessions/ and s03_sessions.py SessionStore
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from nanobot.base.helpers import WORKSPACE_DIR

SESSIONS_DIR = WORKSPACE_DIR / ".sessions"
SESSIONS_INDEX = SESSIONS_DIR / "sessions.json"
TRANSCRIPTS_DIR = SESSIONS_DIR / "transcripts"


class SessionStore:
    """Manages session persistence with JSONL transcripts."""

    def __init__(
        self,
        store_path: Path | None = None,
        transcript_dir: Path | None = None,
    ):
        self.store_path = store_path or SESSIONS_INDEX
        self.transcript_dir = transcript_dir or TRANSCRIPTS_DIR
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict] = self._load_index()

    def _load_index(self) -> dict[str, dict]:
        if not self.store_path.exists():
            return {}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_index(self) -> None:
        self.store_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_session(self, session_key: str) -> dict:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        transcript_file = f"{session_key.replace(':', '_')}_{session_id}.jsonl"
        metadata = {
            "session_key": session_key,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "transcript_file": transcript_file,
        }
        self._index[session_key] = metadata
        self._save_index()
        self.append_transcript(session_key, {"type": "session", "id": session_id, "key": session_key, "created": now})
        return metadata

    def load_session(self, session_key: str) -> dict:
        if session_key not in self._index:
            metadata = self.create_session(session_key)
            return {"metadata": metadata, "history": []}
        metadata = self._index[session_key]
        history = self._rebuild_history(metadata["transcript_file"])
        return {"metadata": metadata, "history": history}

    def save_turn(self, session_key: str, user_msg: str, assistant_blocks: list) -> None:
        if session_key not in self._index:
            self.create_session(session_key)
        now = datetime.now(timezone.utc).isoformat()
        self.append_transcript(session_key, {"type": "user", "content": user_msg, "ts": now})
        for block in assistant_blocks:
            block_type = block.get("type", "unknown") if isinstance(block, dict) else getattr(block, "type", "unknown")
            if block_type == "text":
                text = block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                self.append_transcript(session_key, {"type": "assistant", "content": text, "ts": now})
            elif block_type == "tool_use":
                self.append_transcript(session_key, {
                    "type": "tool_use",
                    "name": block.get("name", ""),
                    "tool_use_id": block.get("id", ""),
                    "input": block.get("input", {}),
                    "ts": now,
                })
            elif block_type == "tool_result":
                self.append_transcript(session_key, {
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "output": block.get("output", ""),
                    "ts": now,
                })
        metadata = self._index[session_key]
        metadata["updated_at"] = now
        metadata["message_count"] = metadata.get("message_count", 0) + 1
        self._save_index()

    def append_transcript(self, session_key: str, entry: dict) -> None:
        metadata = self._index.get(session_key)
        if not metadata:
            return
        filepath = self.transcript_dir / metadata["transcript_file"]
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _rebuild_history(self, transcript_file: str) -> list[dict]:
        """Rebuild OpenAI messages from JSONL transcript."""
        filepath = self.transcript_dir / transcript_file
        if not filepath.exists():
            return []
        messages: list[dict] = []
        pending_tool_uses: list[dict] = []

        def _flush():
            nonlocal pending_tool_uses
            if not pending_tool_uses:
                return
            messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [
                    {"id": tu.get("tool_use_id", ""), "type": "function",
                     "function": {"name": tu.get("name", ""), "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False)}}
                    for tu in pending_tool_uses
                ],
            })
            pending_tool_uses = []

        for line in filepath.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = entry.get("type")
            if t == "session":
                continue
            elif t == "user":
                _flush()
                messages.append({"role": "user", "content": entry.get("content", "")})
            elif t == "assistant":
                _flush()
                messages.append({"role": "assistant", "content": entry.get("content", "")})
            elif t == "tool_use":
                pending_tool_uses.append(entry)
            elif t == "tool_result":
                _flush()
                messages.append({"role": "tool", "tool_call_id": entry.get("tool_use_id", ""), "content": entry.get("output", "")})
        _flush()
        return messages

    def list_sessions(self) -> list[dict]:
        sessions = list(self._index.values())
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def session_exists(self, session_key: str) -> bool:
        return session_key in self._index

    def delete_session(self, session_key: str) -> bool:
        if session_key not in self._index:
            return False
        metadata = self._index.pop(session_key)
        self._save_index()
        filepath = self.transcript_dir / metadata["transcript_file"]
        if filepath.exists():
            filepath.unlink()
        return True
