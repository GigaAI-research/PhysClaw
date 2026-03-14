"""Soul & Memory system.

Provides workspace bootstrap (SOUL.md), memory management (MEMORY.md + daily logs),
hybrid search (TF-IDF + BM25), memory tools, and soul prompt builder.

Reference: OpenClaw s06_soul_memory.py
"""

from nanobot.soul.workspace import (
    AgentWithSoulMemory,
    load_workspace_bootstrap_files,
    BOOTSTRAP_MAX_CHARS,
    BOOTSTRAP_TOTAL_MAX_CHARS,
)
from nanobot.soul.search import MemoryIndexManager, get_memory_manager
from nanobot.soul.tools import (
    build_memory_tools,
    handle_memory_tool,
    MEMORY_TOOL_NAMES,
)
from nanobot.soul.prompt import (
    build_agent_system_prompt,
    build_soul_memory_prompt_builder,
    build_soul_memory_registry,
    run_agent_with_soul_and_memory,
    create_agents_with_soul_memory,
    MEMORY_FLUSH_PROMPT,
)

__all__ = [
    "AgentWithSoulMemory",
    "load_workspace_bootstrap_files",
    "BOOTSTRAP_MAX_CHARS",
    "BOOTSTRAP_TOTAL_MAX_CHARS",
    "MemoryIndexManager",
    "get_memory_manager",
    "build_memory_tools",
    "handle_memory_tool",
    "MEMORY_TOOL_NAMES",
    "build_agent_system_prompt",
    "build_soul_memory_prompt_builder",
    "build_soul_memory_registry",
    "run_agent_with_soul_and_memory",
    "create_agents_with_soul_memory",
    "MEMORY_FLUSH_PROMPT",
]
