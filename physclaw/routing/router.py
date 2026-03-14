"""Message routing: Binding matching and session key construction.

Reference: OpenClaw src/routing/bindings.ts, resolve-route.ts, session-key.ts
"""

from __future__ import annotations

import logging

from nanobot.routing.config import AgentConfig, Binding

log = logging.getLogger("routing")


def build_session_key(
    agent_id: str,
    channel: str,
    account_id: str,
    peer_kind: str,
    peer_id: str,
    dm_scope: str = "per-peer",
) -> str:
    """Build session key based on dm_scope.

    Reference: OpenClaw src/routing/session-key.ts

    dm_scope controls session isolation granularity:
    - "main": all DMs share one session (personal assistant)
    - "per-peer": each sender has independent session (multi-user bot)
    - "per-channel-peer": same user on different channels has independent sessions
    """
    agent_id = agent_id.strip().lower()
    channel = channel.strip().lower()
    peer_id = peer_id.strip().lower()
    peer_kind = peer_kind.strip().lower() or "direct"

    # Group messages always isolated by channel + kind + peerId
    if peer_kind != "direct":
        return f"agent:{agent_id}:{channel}:{peer_kind}:{peer_id}"

    # DM sessions depend on scope
    if dm_scope == "main":
        return f"agent:{agent_id}:main"
    elif dm_scope == "per-peer":
        return f"agent:{agent_id}:direct:{peer_id}"
    elif dm_scope == "per-channel-peer":
        return f"agent:{agent_id}:{channel}:direct:{peer_id}"
    else:
        return f"agent:{agent_id}:direct:{peer_id}"


class MessageRouter:
    """Message router.

    Reference: OpenClaw src/routing/resolve-route.ts

    Resolves which Agent handles an inbound message and the session key to use.

    Resolution flow:
      1. Traverse bindings by priority (descending)
      2. Try matching each rule
      3. First match wins
      4. If no match, use default_agent
    """

    def __init__(
        self,
        agents: dict[str, AgentConfig],
        bindings: list[Binding],
        default_agent: str = "main",
        dm_scope: str = "per-peer",
    ) -> None:
        self.agents = agents
        self.bindings = sorted(bindings, key=lambda b: b.priority, reverse=True)
        self.default_agent = default_agent
        self.dm_scope = dm_scope

    def resolve(
        self,
        channel: str,
        sender: str,
        peer_kind: str = "direct",
        guild_id: str | None = None,
        account_id: str | None = None,
    ) -> tuple[AgentConfig, str]:
        """Resolve which Agent handles this message and the session key."""
        matched_agent_id = self.default_agent

        for binding in self.bindings:
            if self._matches(binding, channel, sender, peer_kind, guild_id, account_id):
                matched_agent_id = binding.agent_id
                log.info(
                    "route: matched %s for channel=%s sender=%s kind=%s",
                    binding, channel, sender, peer_kind,
                )
                break

        agent = self.agents.get(matched_agent_id)
        if agent is None:
            log.warning(
                "route: agent %r not found, falling back to %r",
                matched_agent_id, self.default_agent,
            )
            agent = self.agents[self.default_agent]

        session_key = build_session_key(
            agent_id=agent.id,
            channel=channel,
            account_id=account_id or "default",
            peer_kind=peer_kind,
            peer_id=sender if peer_kind == "direct" else (guild_id or sender),
            dm_scope=self.dm_scope,
        )
        return agent, session_key

    def _matches(
        self,
        binding: Binding,
        channel: str,
        sender: str,
        peer_kind: str,
        guild_id: str | None,
        account_id: str | None,
    ) -> bool:
        """Check if a binding rule matches the inbound message."""
        if binding.channel and binding.channel.lower() != channel.lower():
            return False
        if binding.account_id and binding.account_id.lower() != (account_id or "").lower():
            return False
        if binding.guild_id and binding.guild_id.lower() != (guild_id or "").lower():
            return False
        if binding.peer_id and binding.peer_id.lower() != sender.lower():
            return False
        if binding.peer_kind and binding.peer_kind.lower() != peer_kind.lower():
            return False
        return True

    def describe_bindings(self) -> str:
        """Print all binding rules for debugging."""
        lines = ["Routing bindings (priority desc):"]
        for i, b in enumerate(self.bindings):
            lines.append(f"  [{i}] {b}")
        lines.append(f"  [default] -> {self.default_agent}")
        return "\n".join(lines)
