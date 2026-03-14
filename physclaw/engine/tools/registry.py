"""Composable tool registry and system prompt builder.

ToolRegistry: Plugin-style tool composition -- each module (base tools, memory,
node) creates its own registry, then merges them together.

SystemPromptBuilder: Section-based prompt construction -- each module adds its
own prompt section, and they're concatenated in registration order.

Reference: OpenClaw src/agents/tools/ plugin architecture
Reference: OpenClaw src/agents/system-prompt.ts buildAgentSystemPrompt()
"""

from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """Composable tool registry.

    Each module can create its own ToolRegistry, then merge via merge().

    Usage:
        base = ToolRegistry.from_definitions(TOOLS_OPENAI, TOOL_HANDLERS)
        memory_reg = ToolRegistry()
        memory_reg.register("memory_search", spec, handler)
        all_tools = base.merge(memory_reg)
    """

    def __init__(self) -> None:
        self._specs: list[dict] = []
        self._handlers: dict[str, Callable] = {}

    def register(self, name: str, spec: dict, handler: Callable[..., str]) -> None:
        """Register a tool: definition (OpenAI function spec) + handler."""
        self._specs.append(spec)
        self._handlers[name] = handler

    @property
    def specs(self) -> list[dict]:
        """All tool definitions in OpenAI function-calling format."""
        return list(self._specs)

    def handle(self, tool_name: str, args: dict) -> str | None:
        """Dispatch a tool call. Returns result string; None if not registered."""
        handler = self._handlers.get(tool_name)
        if handler is None:
            return None
        try:
            return handler(**args)
        except TypeError as exc:
            return f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            return f"Error: {tool_name} failed: {exc}"

    def merge(self, other: ToolRegistry) -> ToolRegistry:
        """Merge another ToolRegistry, returning a new combined one."""
        merged = ToolRegistry()
        merged._specs = self._specs + other._specs
        merged._handlers = {**self._handlers, **other._handlers}
        return merged

    @staticmethod
    def from_definitions(specs: list[dict], handlers: dict[str, Callable]) -> ToolRegistry:
        """Create a ToolRegistry from existing specs and handlers."""
        reg = ToolRegistry()
        reg._specs = list(specs)
        reg._handlers = dict(handlers)
        return reg


class SystemPromptBuilder:
    """Section-based system prompt builder.

    Each module adds its own prompt section; build() concatenates them.

    Usage:
        builder = SystemPromptBuilder()
        builder.add_section("base", lambda agent, _: base_prompt)
        builder.add_section("personality", lambda agent, _: f"You are {agent.system_prompt}")
        prompt = builder.build(agent, base_prompt)
    """

    def __init__(self) -> None:
        self._sections: list[tuple[str, Callable]] = []

    def add_section(self, name: str, builder: Callable[..., str]) -> None:
        """Add a prompt section. builder(agent, base_prompt) -> str."""
        self._sections.append((name, builder))

    def build(self, agent: Any, base_prompt: str) -> str:
        """Build full system prompt by concatenating all sections."""
        parts = []
        for _name, builder in self._sections:
            section = builder(agent, base_prompt)
            if section:
                parts.append(section)
        return "\n".join(parts)

    @staticmethod
    def default() -> SystemPromptBuilder:
        """Create default builder (base + personality)."""
        b = SystemPromptBuilder()
        b.add_section("base", lambda agent, base: base)
        b.add_section("personality", lambda agent, _: (
            f"\nPersonality: {agent.system_prompt}" if agent.system_prompt else ""
        ))
        return b
