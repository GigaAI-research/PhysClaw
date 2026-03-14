"""Memory tools: memory_search, memory_get, memory_write.

Reference: OpenClaw src/agents/tools/memory-tool.ts
"""

from __future__ import annotations

import json
from typing import Any

from nanobot.soul.search import (
    MemoryIndexManager,
    get_memory_manager,
    SEARCH_MAX_RESULTS,
    SEARCH_MIN_SCORE,
)

MEMORY_TOOL_NAMES = {"memory_search", "memory_get", "memory_write"}


def build_memory_tools() -> list[dict]:
    """Build memory tool definitions (OpenAI function-calling format)."""
    raw = [
        {
            "name": "memory_search",
            "description": (
                "Mandatory recall step: semantically search MEMORY.md + memory/*.md "
                "before answering questions about prior work, decisions, dates, people, "
                "preferences, or todos; returns top snippets with path + lines. "
                "Use memory_get after to pull only the needed lines and keep context small."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "maxResults": {
                        "type": "integer",
                        "description": f"Max results (default {SEARCH_MAX_RESULTS}).",
                    },
                    "minScore": {
                        "type": "number",
                        "description": f"Min relevance 0-1 (default {SEARCH_MIN_SCORE}).",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "memory_get",
            "description": (
                "Safe snippet read from MEMORY.md or memory/*.md with optional from/lines; "
                "use after memory_search to pull only the needed lines and keep context small."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative path (e.g. 'MEMORY.md', 'memory/2026-03-04.md').",
                    },
                    "from": {
                        "type": "integer",
                        "description": "Start line (1-indexed). Omit to read whole file.",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to read.",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "memory_write",
            "description": (
                "Append a timestamped entry to today's memory/YYYY-MM-DD.md. "
                "Use for preferences, facts, decisions. "
                "(Teaching shortcut — production OpenClaw writes via bash tools.)"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The information to remember.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Tag: preference / fact / decision / todo / person.",
                    },
                },
                "required": ["content"],
            },
        },
    ]
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in raw
    ]


def handle_memory_tool(tool_name: str, params: dict, agent: Any) -> str:
    """Dispatch memory tool call. Returns JSON string."""
    mgr = get_memory_manager(agent)

    if tool_name == "memory_search":
        query = params.get("query", "")
        if not query.strip():
            return json.dumps({"results": [], "error": "Empty query"})
        max_r = params.get("maxResults", SEARCH_MAX_RESULTS)
        min_s = params.get("minScore", SEARCH_MIN_SCORE)
        results = mgr.search(query, max_results=max_r, min_score=min_s)
        return json.dumps({
            "results": results,
            "provider": "tfidf+bm25",
            "model": "hybrid-local",
        })

    if tool_name == "memory_get":
        path = params.get("path", "")
        if not path.strip():
            return json.dumps({"path": "", "text": "", "error": "Path required"})
        result = mgr.read_file(
            path,
            from_line=params.get("from"),
            n_lines=params.get("lines"),
        )
        return json.dumps(result)

    if tool_name == "memory_write":
        content = params.get("content", "")
        if not content.strip():
            return json.dumps({"error": "Empty content"})
        cat = params.get("category", "general")
        rel = mgr.write_daily(content, cat)
        return json.dumps({"status": "saved", "path": rel, "category": cat})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})
