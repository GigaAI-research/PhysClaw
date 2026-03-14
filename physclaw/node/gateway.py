"""NodeGateway: WebSocket gateway with Node management.

Extends SoulMemoryGateway with:
  - NodePairingStore: pairing persistence
  - NodeRegistry: runtime connected node management
  - Node WebSocket auth and message handling
  - node.* RPC methods

Inheritance: NodeGateway -> SoulMemoryGateway -> RoutingGateway

Reference: OpenClaw src/gateway/server-methods/nodes.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from nanobot.base.helpers import WORKSPACE_DIR
from nanobot.routing.server import ConnectedClient
from nanobot.routing.protocol import make_event
from nanobot.routing.router import MessageRouter
from nanobot.soul.gateway import SoulMemoryGateway
from nanobot.soul.workspace import AgentWithSoulMemory
from nanobot.node.info import NodeInfo
from nanobot.node.pairing import NodePairingStore
from nanobot.node.registry import NodeRegistry, ConnectedNode, NODE_INVOKE_TIMEOUT
from nanobot.node.events import handle_node_event

log = logging.getLogger("gateway-node")


class NodeGateway(SoulMemoryGateway):
    """WebSocket gateway with Node management.

    Inherits all SoulMemoryGateway methods and adds:
      - Node pairing (request / approve / reject / verify)
      - Node connection management (auth / register / unregister)
      - Node command invocation (invoke)
      - Node event handling and broadcast
      - node.* RPC methods
    """

    def __init__(
        self,
        host: str,
        port: int,
        router: MessageRouter,
        sessions: Any,
        soul_agents: dict[str, AgentWithSoulMemory],
        token: str = "",
        *,
        node_store_path: Path | None = None,
    ) -> None:
        super().__init__(host, port, router, sessions, soul_agents, token)

        node_dir = node_store_path or (WORKSPACE_DIR / "nodes")
        if node_store_path and node_store_path.suffix == ".json":
            pairing_path = node_store_path
        else:
            node_dir.mkdir(parents=True, exist_ok=True)
            pairing_path = node_dir / "pairing.json"

        self._pairing_store = NodePairingStore(pairing_path)
        self._node_registry = NodeRegistry()

        # Register Node RPC methods
        self._methods["node.list"] = self._handle_node_list
        self._methods["node.describe"] = self._handle_node_describe
        self._methods["node.rename"] = self._handle_node_rename
        self._methods["node.invoke"] = self._handle_node_invoke
        self._methods["node.pair.request"] = self._handle_node_pair_request
        self._methods["node.pair.list"] = self._handle_node_pair_list
        self._methods["node.pair.approve"] = self._handle_node_pair_approve
        self._methods["node.pair.reject"] = self._handle_node_pair_reject

    @property
    def node_registry(self) -> NodeRegistry:
        return self._node_registry

    @property
    def pairing_store(self) -> NodePairingStore:
        return self._pairing_store

    # -- Node WebSocket message handling --

    async def _on_node_auth(self, client: ConnectedClient, msg: dict) -> None:
        """Handle Node auth message."""
        node_id = msg.get("node_id", "").strip()
        token = msg.get("token", "")
        info_dict = msg.get("info", {})

        if not node_id or not token:
            await client.ws.send(
                json.dumps(
                    {"type": "auth.failed", "reason": "missing node_id or token"}
                )
            )
            return

        paired = self._pairing_store.verify_token(node_id, token)
        if paired is None:
            log.warning("node-auth: failed for %s", node_id)
            await client.ws.send(
                json.dumps({"type": "auth.failed", "reason": "invalid token"})
            )
            return

        info = NodeInfo.from_dict(info_dict)
        info.node_id = node_id

        connected_node = ConnectedNode(node_id=node_id, info=info, ws=client.ws)
        self._node_registry.register(connected_node)

        self._pairing_store.update_metadata(
            node_id,
            {
                "display_name": info.display_name or paired.get("display_name"),
                "platform": info.platform,
                "version": info.version,
                "caps": info.caps,
                "commands": info.commands,
                "permissions": info.permissions,
                "last_connected_at": time.time(),
            },
        )

        await client.ws.send(json.dumps({"type": "auth.ok"}))
        log.info(
            "node-auth: %s authenticated (%s)",
            node_id,
            info.display_name or "unnamed",
        )

        event_str = make_event(
            "node.connected",
            {
                "node_id": node_id,
                "display_name": info.display_name,
                "platform": info.platform,
            },
        )
        for c in list(self.clients.values()):
            if c is not client:
                try:
                    await c.ws.send(event_str)
                except Exception:
                    pass

    async def _on_node_tick(self, client: ConnectedClient, msg: dict) -> None:
        node_id = msg.get("node_id", "")
        if node_id:
            self._node_registry.update_tick(node_id)

    async def _on_node_event(self, client: ConnectedClient, msg: dict) -> None:
        node_id = msg.get("node_id", "")
        if not node_id:
            for n in self._node_registry.list_nodes():
                if n.ws is client.ws:
                    node_id = n.node_id
                    break

        event = msg.get("event", "")
        payload = msg.get("payload", {})

        if node_id and self._node_registry.on_node_event is not None:
            try:
                self._node_registry.on_node_event(node_id, event, payload)
            except Exception:
                log.exception("node-gateway: on_node_event callback error")

        broadcast_text = handle_node_event(node_id, event, payload)
        if broadcast_text:
            event_str = make_event(
                "node.event",
                {"node_id": node_id, "event": event, "text": broadcast_text},
            )
            for c in list(self.clients.values()):
                try:
                    await c.ws.send(event_str)
                except Exception:
                    pass

    async def _on_invoke_result(self, client: ConnectedClient, msg: dict) -> None:
        invoke_id = msg.get("invoke_id", "")
        result = msg.get("result", {})
        if invoke_id:
            self._node_registry.handle_invoke_result(invoke_id, result)

    # -- Override message dispatch --

    async def _dispatch(self, client: ConnectedClient, raw: str) -> None:
        """Extend dispatch: handle Node message types before JSON-RPC."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await super()._dispatch(client, raw)
            return

        msg_type = msg.get("type", "")

        if msg_type == "node.auth":
            await self._on_node_auth(client, msg)
            return
        elif msg_type == "node.tick":
            await self._on_node_tick(client, msg)
            return
        elif msg_type == "node.event":
            await self._on_node_event(client, msg)
            return
        elif msg_type == "invoke.result":
            await self._on_invoke_result(client, msg)
            return

        await super()._dispatch(client, raw)

    async def _on_client_disconnect(self, client: ConnectedClient) -> None:
        """On disconnect, unregister if it was a Node."""
        for node in self._node_registry.list_nodes():
            if node.ws is client.ws:
                self._node_registry.unregister(node.node_id)
                event_str = make_event(
                    "node.disconnected",
                    {
                        "node_id": node.node_id,
                        "display_name": node.info.display_name,
                    },
                )
                for c in list(self.clients.values()):
                    try:
                        await c.ws.send(event_str)
                    except Exception:
                        pass
                break
        await super()._on_client_disconnect(client)

    # -- RPC Handlers --

    async def _handle_node_list(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        """node.list — List all online + paired Nodes."""
        online = self._node_registry.list_nodes()
        online_ids = {n.node_id for n in online}

        pairing = self._pairing_store.list_pairing()
        paired_nodes = pairing.get("paired", [])

        result = []
        for n in online:
            result.append(
                {
                    "node_id": n.node_id,
                    "display_name": n.info.display_name,
                    "platform": n.info.platform,
                    "version": n.info.version,
                    "caps": n.info.caps,
                    "commands": n.info.commands,
                    "online": True,
                    "connected_at": n.connected_at,
                    "connected_seconds": int(time.time() - n.connected_at),
                }
            )
        for p in paired_nodes:
            nid = p.get("node_id", "")
            if nid not in online_ids:
                result.append(
                    {
                        "node_id": nid,
                        "display_name": p.get("display_name", ""),
                        "platform": p.get("platform", ""),
                        "version": p.get("version", ""),
                        "caps": p.get("caps", []),
                        "online": False,
                        "paired_at": p.get("paired_at"),
                        "last_connected_at": p.get("last_connected_at"),
                    }
                )
        return {"nodes": result}

    async def _handle_node_describe(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        """node.describe — Get Node details."""
        node_id = params.get("node_id", "").strip()
        if not node_id:
            return {"error": "missing node_id"}

        node = self._node_registry.get(node_id)
        if node is not None:
            return {
                "node_id": node_id,
                "online": True,
                **node.info.to_dict(),
                "connected_at": node.connected_at,
                "connected_seconds": int(time.time() - node.connected_at),
                "last_tick_at": node.last_tick_at,
            }

        pairing = self._pairing_store.list_pairing()
        for p in pairing.get("paired", []):
            if p.get("node_id") == node_id:
                return {
                    "node_id": node_id,
                    "online": False,
                    "display_name": p.get("display_name", ""),
                    "platform": p.get("platform", "?"),
                    "paired_at": p.get("paired_at"),
                    "last_connected_at": p.get("last_connected_at"),
                }

        return {"error": f"node {node_id} not found"}

    async def _handle_node_rename(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        node_id = params.get("node_id", "").strip()
        name = params.get("display_name", "").strip()
        if not node_id or not name:
            return {"error": "missing node_id or display_name"}

        result = self._pairing_store.rename_node(node_id, name)
        if result is None:
            return {"error": f"node {node_id} not found"}

        node = self._node_registry.get(node_id)
        if node is not None:
            node.info.display_name = name
        return {"ok": True, "node_id": node_id, "display_name": name}

    async def _handle_node_invoke(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        """node.invoke — Send command to a Node."""
        node_id = params.get("node_id", "").strip()
        command = params.get("command", "").strip()
        args = params.get("args", {})
        timeout = params.get("timeout", NODE_INVOKE_TIMEOUT)

        if not node_id:
            return {"error": "missing node_id"}
        if not command:
            return {"error": "missing command"}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._node_registry.invoke(node_id, command, args, timeout),
        )
        return result

    async def _handle_node_pair_request(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        node_id = params.get("node_id", "").strip()
        if not node_id:
            return {"error": "missing node_id"}
        info = NodeInfo(
            node_id=node_id,
            display_name=params.get("display_name", ""),
            platform=params.get("platform", ""),
            version=params.get("version", ""),
            caps=params.get("caps", []),
            commands=params.get("commands", []),
        )
        return self._pairing_store.request_pairing(info)

    async def _handle_node_pair_list(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        return self._pairing_store.list_pairing()

    async def _handle_node_pair_approve(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        request_id = params.get("request_id", "").strip()
        if not request_id:
            return {"error": "missing request_id"}
        result = self._pairing_store.approve(request_id)
        if result is None:
            return {"error": f"request {request_id} not found or expired"}
        return result

    async def _handle_node_pair_reject(
        self, client: ConnectedClient, params: dict
    ) -> dict:
        request_id = params.get("request_id", "").strip()
        if not request_id:
            return {"error": "missing request_id"}
        result = self._pairing_store.reject(request_id)
        if result is None:
            return {"error": f"request {request_id} not found"}
        return result
