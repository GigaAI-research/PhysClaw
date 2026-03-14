"""SoulMemoryGateway: WebSocket gateway with Soul+Memory.

Extends RoutingGateway with soul.get, memory.status methods.

Reference: OpenClaw src/gateway/server.impl.ts
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from nanobot.routing.server import RoutingGateway, ConnectedClient
from nanobot.routing.protocol import make_event
from nanobot.routing.router import MessageRouter
from nanobot.llm.llm_client import LLMClientError
from nanobot.soul.workspace import AgentWithSoulMemory
from nanobot.soul.search import get_memory_manager
from nanobot.soul.prompt import run_agent_with_soul_and_memory

log = logging.getLogger("gateway-with-memory")


class SoulMemoryGateway(RoutingGateway):
    """Gateway server with Soul+Memory functionality.

    Inherits all RoutingGateway methods and adds:
    - chat.send uses run_agent_with_soul_and_memory
    - memory.status: query Agent's Memory status
    - soul.get: view Agent's SOUL.md
    """

    def __init__(
        self,
        host: str,
        port: int,
        router: MessageRouter,
        sessions: Any,
        soul_agents: dict[str, AgentWithSoulMemory],
        token: str = "",
    ) -> None:
        super().__init__(host, port, router, sessions, token)
        self.soul_agents = soul_agents
        self._soul_agents = soul_agents
        self._sessions = sessions

        # Override s05 methods
        self._methods["chat.send"] = self._handle_chat_send
        self._methods["health"] = self._handle_health
        self._methods["routing.resolve"] = self._handle_routing_resolve
        # New s06 methods
        self._methods["memory.status"] = self._handle_memory_status
        self._methods["soul.get"] = self._handle_soul_get

    def _get_soul_agent(self, agent_id: str) -> AgentWithSoulMemory:
        """Get AgentWithSoulMemory by agent_id."""
        if agent_id in self.soul_agents:
            return self.soul_agents[agent_id]
        acfg = self.router.agents.get(agent_id)
        if acfg is None:
            acfg = self.router.agents[self.router.default_agent]
        a = AgentWithSoulMemory(
            id=acfg.id,
            model=acfg.model,
            system_prompt=acfg.system_prompt,
            tools=acfg.tools,
        )
        self.soul_agents[a.id] = a
        return a

    async def _handle_health(self, client: ConnectedClient, params: dict) -> dict:
        """health -- Health check (adds features marker)."""
        result = await super()._handle_health(client, params)
        result["features"] = ["soul", "memory"]
        return result

    async def _handle_chat_send(self, client: ConnectedClient, params: dict) -> dict:
        """chat.send -- Uses run_agent_with_soul_and_memory."""
        text = params.get("text", "").strip()
        if not text:
            raise ValueError("'text' is required")

        channel = params.get("channel", client.channel)
        sender = params.get("sender", client.sender)
        peer_kind = params.get("peer_kind", client.peer_kind)
        guild_id = params.get("guild_id", client.guild_id) or None
        account_id = params.get("account_id", client.account_id) or None

        agent_config, session_key = self.router.resolve(
            channel=channel,
            sender=sender,
            peer_kind=peer_kind,
            guild_id=guild_id,
            account_id=account_id,
        )
        log.info("chat.send: routed to agent=%s session=%s", agent_config.id, session_key)

        await client.ws.send(make_event("chat.typing", {
            "session_key": session_key,
            "agent_id": agent_config.id,
        }))

        soul_agent = self._get_soul_agent(agent_config.id)

        try:
            assistant_text = await asyncio.to_thread(
                run_agent_with_soul_and_memory,
                soul_agent,
                self.sessions,
                session_key,
                text,
            )
        except LLMClientError as e:
            log.warning("LLM request failed agent=%s: %s", soul_agent.id, e)
            raise ValueError(f"LLM request failed: {e}") from e

        session_data = self.sessions.load_session(session_key)
        message_count = len(session_data["history"])

        return {
            "text": assistant_text,
            "agent_id": soul_agent.id,
            "session_key": session_key,
            "message_count": message_count,
        }

    async def _handle_routing_resolve(self, client: ConnectedClient, params: dict) -> dict:
        """routing.resolve -- Adds Soul/Memory status info."""
        result = await super()._handle_routing_resolve(client, params)
        agent_id = result.get("agent_id", self.router.default_agent)
        soul_agent = self._get_soul_agent(agent_id)
        has_soul = soul_agent.soul_path.exists()
        mgr = get_memory_manager(soul_agent)
        has_memory = bool(mgr.load_evergreen())
        result["has_soul"] = has_soul
        result["has_memory"] = has_memory
        result["workspace"] = str(soul_agent.workspace_dir)
        return result

    async def _handle_memory_status(self, client: ConnectedClient, params: dict) -> dict:
        """memory.status -- Query Agent's Memory status."""
        agent_id = params.get("agent_id", self.router.default_agent)
        soul_agent = self._get_soul_agent(agent_id)
        mgr = get_memory_manager(soul_agent)
        evergreen = mgr.load_evergreen()
        recent = mgr.get_recent_daily(days=7)
        return {
            "agent_id": agent_id,
            "workspace": str(soul_agent.workspace_dir),
            "memory_md_chars": len(evergreen),
            "recent_daily_count": len(recent),
            "recent_daily": [
                {"date": e["date"], "lines": e["content"].count("\n") + 1}
                for e in recent
            ],
        }

    async def _handle_soul_get(self, client: ConnectedClient, params: dict) -> dict:
        """soul.get -- View Agent's SOUL.md."""
        agent_id = params.get("agent_id", self.router.default_agent)
        soul_agent = self._get_soul_agent(agent_id)
        if soul_agent.soul_path.exists():
            content = soul_agent.soul_path.read_text(encoding="utf-8").strip()
            return {"agent_id": agent_id, "soul": content, "exists": True}
        return {"agent_id": agent_id, "soul": "", "exists": False}
