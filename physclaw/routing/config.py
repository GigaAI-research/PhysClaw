"""Agent configuration and routing config loader.

Reference: OpenClaw src/config/types.agents.ts
Reference: OpenClaw s05_gateway.py AgentConfig, Binding, load_routing_config
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("config")

MODEL = os.getenv("DEEPSEEK_DEFAULT_MODEL", "deepseek-chat")


@dataclass
class AgentConfig:
    """Configuration for a single Agent."""

    id: str
    model: str
    system_prompt: str
    tools: list[dict] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"AgentConfig(id={self.id!r}, model={self.model!r})"


@dataclass
class Binding:
    """Routing binding rule.

    Fields set to None act as wildcards; higher priority matches first.

    Reference: OpenClaw src/routing/bindings.ts
    """

    channel: str | None = None
    account_id: str | None = None
    peer_id: str | None = None       # Peer/group ID
    peer_kind: str | None = None     # "direct" (DM) or "group"
    guild_id: str | None = None
    agent_id: str = "main"
    priority: int = 0

    def __repr__(self) -> str:
        conditions = []
        if self.channel:
            conditions.append(f"channel={self.channel}")
        if self.account_id:
            conditions.append(f"account={self.account_id}")
        if self.guild_id:
            conditions.append(f"guild={self.guild_id}")
        if self.peer_id:
            conditions.append(f"peer={self.peer_id}")
        if self.peer_kind:
            conditions.append(f"kind={self.peer_kind}")
        cond_str = ", ".join(conditions) if conditions else "*"
        return f"Binding({cond_str} -> {self.agent_id}, p={self.priority})"


DEFAULT_CONFIG: dict[str, Any] = {
    "agents": [
        {
            "id": "main",
            "model": MODEL,
            "system_prompt": "You are a helpful general assistant.",
        },
        {
            "id": "alice",
            "model": MODEL,
            "system_prompt": (
                "You are Alice, a creative writing assistant. "
                "You speak in a literary, poetic style and help with creative writing tasks."
            ),
        },
        {
            "id": "bob",
            "model": MODEL,
            "system_prompt": (
                "You are Bob, a technical assistant. "
                "You are precise and methodical, focusing on code and engineering topics."
            ),
        },
    ],
    "bindings": [
        {"peer_id": "user-alice-fan", "agent_id": "alice", "priority": 40},
        {"guild_id": "dev-server", "agent_id": "bob", "priority": 30},
        {"channel": "telegram", "agent_id": "main", "priority": 10},
        {"channel": "discord", "agent_id": "main", "priority": 10},
    ],
    "default_agent": "main",
    "dm_scope": "per-peer",
}


def load_routing_config(
    config_path: str | None = None,
) -> tuple[dict[str, AgentConfig], list[Binding], str, str]:
    """Load routing config. Uses file if specified, otherwise defaults."""
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        log.info("loaded config from %s", config_path)
    else:
        raw = DEFAULT_CONFIG
        log.info("using default config (no config file)")

    # Parse agent configs
    agents: dict[str, AgentConfig] = {}
    for a in raw.get("agents", []):
        cfg = AgentConfig(
            id=a["id"],
            model=a.get("model", MODEL),
            system_prompt=a.get("system_prompt", "You are a helpful assistant."),
            tools=a.get("tools", []),
        )
        agents[cfg.id] = cfg

    # Parse binding rules
    bindings: list[Binding] = []
    for b in raw.get("bindings", []):
        binding = Binding(
            channel=b.get("channel"),
            account_id=b.get("account_id"),
            peer_id=b.get("peer_id"),
            peer_kind=b.get("peer_kind"),
            guild_id=b.get("guild_id"),
            agent_id=b.get("agent_id", "main"),
            priority=b.get("priority", 0),
        )
        bindings.append(binding)

    default_agent = raw.get("default_agent", "main")
    dm_scope = raw.get("dm_scope", "per-peer")
    return agents, bindings, default_agent, dm_scope
