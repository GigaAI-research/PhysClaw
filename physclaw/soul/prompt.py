"""Soul prompt builder and agent runner with soul+memory integration.

Reference: OpenClaw src/agents/system-prompt.ts buildAgentSystemPrompt()
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable

from nanobot.routing.config import AgentConfig
from nanobot.engine.tools.registry import ToolRegistry, SystemPromptBuilder
from nanobot.soul.workspace import (
    AgentWithSoulMemory,
    load_workspace_bootstrap_files,
)
from nanobot.soul.search import get_memory_manager
from nanobot.soul.tools import build_memory_tools, handle_memory_tool

log = logging.getLogger("soul")

# Memory flush prompt
MEMORY_FLUSH_PROMPT = (
    "Pre-compaction memory flush. Store durable memories now "
    "(use memory/YYYY-MM-DD.md; create memory/ if needed). "
    "IMPORTANT: If the file already exists, APPEND new content only "
    "and do not overwrite existing entries."
)


def build_soul_memory_prompt_builder(agent: AgentWithSoulMemory) -> SystemPromptBuilder:
    """Create SystemPromptBuilder with Soul+Memory sections.

    Sections:
      base        -> base system prompt (identity + tools)
      personality -> agent.system_prompt
      memory      -> Memory Recall instructions
      time        -> date + workspace
      context     -> SOUL.md + MEMORY.md (project context files)
      recent      -> recent memory awareness
    """
    pb = SystemPromptBuilder()

    pb.add_section("base", lambda ag, base: base)
    pb.add_section("personality", lambda ag, _: (
        f"\nPersonality: {ag.system_prompt}" if ag.system_prompt else ""
    ))
    pb.add_section("memory_recall", lambda ag, _: (
        "\n## Memory Recall\n"
        "Before answering anything about prior work, decisions, dates, people, "
        "preferences, or todos: run memory_search on MEMORY.md + memory/*.md; "
        "then use memory_get to pull only the needed lines. "
        "If low confidence after search, say you checked.\n"
        "Citations: include Source: <path#Lstart-Lend> when it helps the user "
        "verify memory snippets."
    ))

    def _time_section(ag: AgentConfig, _base: str) -> str:
        ws = getattr(ag, 'workspace_dir', '')
        return (
            f"\n## Time\nCurrent date: {date.today().isoformat()}\n"
            f"\n## Workspace\nWorking directory: {ws}\n"
            "Treat this directory as the single global workspace for memory files."
        )
    pb.add_section("time_workspace", _time_section)

    def _context_files(ag: AgentConfig, _base: str) -> str:
        ws = getattr(ag, 'workspace_dir', None)
        if not ws:
            return ""
        bootstrap_files = load_workspace_bootstrap_files(ws)
        if not bootstrap_files:
            return ""
        parts = [
            "\n## Project Context Files\n"
            "The following project context files have been loaded from the workspace.\n"
            "If SOUL.md is present, embody its persona — speak, think, and "
            "respond in the style it defines.\n"
        ]
        for bf in bootstrap_files:
            parts.append(f"\n### {bf['name']}\n\n{bf['content']}")
        return "\n".join(parts)
    pb.add_section("context_files", _context_files)

    def _recent_memory(ag: AgentConfig, _base: str) -> str:
        mgr = get_memory_manager(ag)
        recent = mgr.get_recent_daily(days=2)
        if not recent:
            return ""
        lines = ["\n## Recent Memory (Awareness Only)"]
        for entry in recent:
            snippet = entry["content"][:500]
            lines.append(f"\n### {entry['date']}\n{snippet}")
        return "\n".join(lines)
    pb.add_section("recent_memory", _recent_memory)

    return pb


def build_agent_system_prompt(agent: AgentWithSoulMemory, base_prompt: str) -> str:
    """Build complete system prompt with Soul+Memory."""
    pb = build_soul_memory_prompt_builder(agent)
    return pb.build(agent, base_prompt)


def build_soul_memory_registry(agent: AgentWithSoulMemory) -> ToolRegistry:
    """Create ToolRegistry with base tools + memory tools."""
    from nanobot.engine.tools.definitions import TOOLS_OPENAI, TOOL_HANDLERS

    base = ToolRegistry.from_definitions(TOOLS_OPENAI, TOOL_HANDLERS)
    memory_reg = ToolRegistry()

    for tool_spec in build_memory_tools():
        name = tool_spec["function"]["name"]

        def _make_handler(tool_name: str) -> Callable:
            def handler(**kwargs: Any) -> str:
                return handle_memory_tool(tool_name, kwargs, agent)
            return handler

        memory_reg.register(name, tool_spec, _make_handler(name))

    return base.merge(memory_reg)


def run_agent_with_soul_and_memory(
    agent: AgentWithSoulMemory,
    session_store: Any,
    session_key: str,
    user_text: str,
) -> str:
    """Process one user turn with Soul+Memory integration."""
    from nanobot.engine.loop import run_agent_with_tools

    registry = build_soul_memory_registry(agent)
    prompt_builder = build_soul_memory_prompt_builder(agent)

    return run_agent_with_tools(
        agent,
        session_store,
        session_key,
        user_text,
        registry=registry,
        prompt_builder=prompt_builder,
    )


def create_agents_with_soul_memory(
    config_path: str | None = None,
) -> tuple[dict[str, AgentWithSoulMemory], list, str, str]:
    """Load agents from config and upgrade to AgentWithSoulMemory."""
    from nanobot.routing.config import load_routing_config

    agents, bindings, default_agent, dm_scope = load_routing_config(config_path)

    result: dict[str, AgentWithSoulMemory] = {}
    for aid, acfg in agents.items():
        a = AgentWithSoulMemory(
            id=acfg.id,
            model=acfg.model,
            system_prompt=acfg.system_prompt,
            tools=acfg.tools,
        )
        result[aid] = a
        log.info("agent %s  workspace=%s", aid, a.workspace_dir)

    return result, bindings, default_agent, dm_scope
