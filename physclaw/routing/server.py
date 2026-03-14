"""WebSocket gateway server with routing.

Reference: OpenClaw src/gateway/server.impl.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from nanobot.routing.protocol import (
    JSONRPC_VERSION, PARSE_ERROR, INVALID_REQUEST,
    METHOD_NOT_FOUND, INTERNAL_ERROR, AUTH_ERROR,
    make_result, make_error, make_event,
)
from nanobot.routing.router import MessageRouter
from nanobot.engine.loop import run_agent_with_tools
from nanobot.llm.llm_client import LLMClientError

log = logging.getLogger("gateway")


@dataclass
class ConnectedClient:
    """Connected client state."""

    ws: Any  # ServerConnection
    client_id: str
    channel: str = "websocket"
    sender: str = ""
    peer_kind: str = "direct"
    guild_id: str = ""
    account_id: str = ""
    connected_at: float = field(default_factory=time.time)


class RoutingGateway:
    """WebSocket gateway server with message routing.

    Reference: OpenClaw src/gateway/server.impl.ts
    """

    def __init__(
        self,
        host: str,
        port: int,
        router: MessageRouter,
        sessions: Any,
        token: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.router = router
        self.sessions = sessions
        self.token = token
        self.clients: dict[str, ConnectedClient] = {}
        self._start_time = time.time()

        # JSON-RPC method routing table
        self._methods: dict[str, Any] = {
            "health": self._handle_health,
            "chat.send": self._handle_chat_send,
            "chat.history": self._handle_chat_history,
            "routing.resolve": self._handle_routing_resolve,
            "routing.bindings": self._handle_routing_bindings,
            "sessions.list": self._handle_sessions_list,
            "identify": self._handle_identify,
        }

    def _authenticate(self, headers: Any) -> bool:
        """Verify Bearer Token authentication."""
        if not self.token:
            return True
        auth_header = headers.get("Authorization", "")
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return False
        return parts[1].strip() == self.token

    async def _handle_connection(self, ws: Any) -> None:
        """Handle a single WebSocket connection lifecycle."""
        import websockets

        client_id = str(uuid.uuid4())[:8]

        if not self._authenticate(ws.request.headers if ws.request else {}):
            await ws.send(make_error(None, AUTH_ERROR, "Authentication failed"))
            await ws.close(4001, "Unauthorized")
            return

        client = ConnectedClient(ws=ws, client_id=client_id)
        self.clients[client_id] = client
        log.info("client %s: connected (total: %d)", client_id, len(self.clients))

        await ws.send(make_event("connect.welcome", {"client_id": client_id}))

        try:
            async for raw_message in ws:
                if isinstance(raw_message, bytes):
                    raw_message = raw_message.decode("utf-8")
                await self._dispatch(client, raw_message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self._on_client_disconnect(client)
            del self.clients[client_id]
            log.info("client %s: disconnected", client_id)

    async def _on_client_disconnect(self, client: ConnectedClient) -> None:
        """Client disconnect callback hook. Subclasses can override."""
        pass

    async def _dispatch(self, client: ConnectedClient, raw: str) -> None:
        """JSON-RPC request dispatcher."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await client.ws.send(make_error(None, PARSE_ERROR, "Invalid JSON"))
            return

        if not isinstance(msg, dict) or msg.get("jsonrpc") != JSONRPC_VERSION:
            await client.ws.send(make_error(msg.get("id"), INVALID_REQUEST, "Invalid JSON-RPC"))
            return

        req_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        log.info("client %s: -> %s (id=%s)", client.client_id, method, req_id)

        handler = self._methods.get(method)
        if handler is None:
            await client.ws.send(make_error(req_id, METHOD_NOT_FOUND, f"Unknown: {method}"))
            return

        try:
            result = await handler(client, params)
            await client.ws.send(make_result(req_id, result))
        except Exception as exc:
            log.exception("method %s error", method)
            await client.ws.send(make_error(req_id, INTERNAL_ERROR, str(exc)))

    # -- RPC method implementations --

    async def _handle_health(self, client: ConnectedClient, params: dict) -> dict:
        """health -- Health check."""
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "connected_clients": len(self.clients),
            "agents": list(self.router.agents.keys()),
        }

    async def _handle_identify(self, client: ConnectedClient, params: dict) -> dict:
        """identify -- Client declares its channel and identity info."""
        client.channel = params.get("channel", "websocket")
        client.sender = params.get("sender", client.client_id)
        client.peer_kind = params.get("peer_kind", "direct")
        client.guild_id = params.get("guild_id", "")
        client.account_id = params.get("account_id", "")
        log.info(
            "client %s: identified as channel=%s sender=%s kind=%s",
            client.client_id, client.channel, client.sender, client.peer_kind,
        )
        return {"identified": True, "channel": client.channel, "sender": client.sender}

    async def _handle_chat_send(self, client: ConnectedClient, params: dict) -> dict:
        """chat.send -- Route message to agent, call LLM, return response."""
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

        try:
            assistant_text = await asyncio.to_thread(
                run_agent_with_tools,
                agent_config,
                self.sessions,
                session_key,
                text,
            )
        except LLMClientError as e:
            log.warning("LLM request failed agent=%s: %s", agent_config.id, e)
            raise ValueError(f"LLM request failed: {e}") from e

        session_data = self.sessions.load_session(session_key)
        message_count = len(session_data["history"])

        return {
            "text": assistant_text,
            "agent_id": agent_config.id,
            "session_key": session_key,
            "message_count": message_count,
        }

    async def _handle_chat_history(self, client: ConnectedClient, params: dict) -> dict:
        """chat.history -- Get session message history."""
        session_key = params.get("session_key", "")
        if not session_key:
            raise ValueError("'session_key' is required")
        session_data = self.sessions.load_session(session_key)
        messages = session_data["history"]
        limit = params.get("limit", 50)
        if len(messages) > limit:
            messages = messages[-limit:]
        return {"session_key": session_key, "messages": messages, "total": len(session_data["history"])}

    async def _handle_routing_resolve(self, client: ConnectedClient, params: dict) -> dict:
        """routing.resolve -- Diagnostic: see which agent handles a message."""
        channel = params.get("channel", "websocket")
        sender = params.get("sender", "anonymous")
        peer_kind = params.get("peer_kind", "direct")
        guild_id = params.get("guild_id")
        account_id = params.get("account_id")

        agent_config, session_key = self.router.resolve(
            channel=channel,
            sender=sender,
            peer_kind=peer_kind,
            guild_id=guild_id,
            account_id=account_id,
        )
        return {
            "agent_id": agent_config.id,
            "agent_model": agent_config.model,
            "session_key": session_key,
            "system_prompt_preview": (
                agent_config.system_prompt[:100] + "..."
                if len(agent_config.system_prompt) > 100
                else agent_config.system_prompt
            ),
        }

    async def _handle_routing_bindings(self, client: ConnectedClient, params: dict) -> dict:
        """routing.bindings -- List all binding rules."""
        return {
            "bindings": [
                {
                    "channel": b.channel,
                    "account_id": b.account_id,
                    "peer_id": b.peer_id,
                    "peer_kind": b.peer_kind,
                    "guild_id": b.guild_id,
                    "agent_id": b.agent_id,
                    "priority": b.priority,
                }
                for b in self.router.bindings
            ],
            "default_agent": self.router.default_agent,
            "dm_scope": self.router.dm_scope,
        }

    async def _handle_sessions_list(self, client: ConnectedClient, params: dict) -> dict:
        """sessions.list -- List all active sessions."""
        raw = self.sessions.list_sessions()
        sessions = []
        for m in raw:
            sk = m.get("session_key", "")
            parts = sk.split(":") if sk else []
            agent_id = parts[1] if len(parts) > 1 else "main"
            sessions.append({
                "session_key": sk,
                "agent_id": agent_id,
                "message_count": m.get("message_count", 0),
                "last_active": m.get("updated_at", ""),
            })
        return {"sessions": sessions}

    async def start(self) -> None:
        """Start WebSocket server and enter event loop."""
        import websockets

        log.info("Gateway starting on ws://%s:%d", self.host, self.port)
        log.info("\n%s", self.router.describe_bindings())

        async with websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
        ):
            log.info("Gateway ready. Waiting for connections...")
            await asyncio.Future()
