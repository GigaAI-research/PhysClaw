"""NodeRegistry: runtime registry of connected nodes.

NodePairingStore manages "who is allowed to connect" (persistent);
NodeRegistry manages "who is currently connected" (runtime).

Also handles invoke tracking: send command to Node, wait for response.

Reference: OpenClaw src/gateway/node-registry.ts
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from nanobot.node.info import NodeInfo, DEFAULT_ALLOWED_COMMANDS

log = logging.getLogger(__name__)

# Invoke default timeout (seconds)
# Reference: OpenClaw node-registry.ts DEFAULT_INVOKE_TIMEOUT_MS = 30_000
NODE_INVOKE_TIMEOUT = 30


@dataclass
class ConnectedNode:
    """Runtime info for a connected Node."""

    node_id: str
    info: NodeInfo
    ws: Any  # WebSocket connection
    connected_at: float = field(default_factory=time.time)
    last_tick_at: float = 0.0

    def __repr__(self) -> str:
        name = self.info.display_name or self.node_id[:8]
        elapsed = time.time() - self.connected_at
        return f"ConnectedNode({name}, up={elapsed:.0f}s)"


@dataclass
class PendingInvoke:
    """A pending invoke request waiting for Node response.

    Gateway sends invoke → creates PendingInvoke → waits for result.
    Node replies invoke.result → matched by invoke_id → result set.
    """

    invoke_id: str
    node_id: str
    command: str
    created_at: float = field(default_factory=time.time)
    result: dict | None = None
    event: threading.Event = field(default_factory=threading.Event)


class NodeRegistry:
    """Runtime registry of connected nodes.

    Reference: OpenClaw src/gateway/node-registry.ts

    Thread-safe via internal lock.

    Responsibilities:
      1. register / unregister: manage Node connections
      2. get / list_nodes: query online Nodes
      3. invoke: send command to Node and wait for result
      4. handle_invoke_result: process Node's invoke reply
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, ConnectedNode] = {}
        self._pending_invokes: dict[str, PendingInvoke] = {}

        # Lifecycle callbacks for external consumers (e.g. NodeEventSource)
        self.on_node_connect: Callable[[str, NodeInfo], None] | None = None
        self.on_node_disconnect: Callable[[str, NodeInfo], None] | None = None
        self.on_node_tick: Callable[[str], None] | None = None
        self.on_node_event: Callable[[str, str, dict], None] | None = None

    def register(self, node: ConnectedNode) -> None:
        """Register a newly connected Node."""
        with self._lock:
            old = self._nodes.get(node.node_id)
            if old is not None:
                log.warning(
                    "node-registry: replacing existing connection for %s",
                    node.node_id,
                )
            self._nodes[node.node_id] = node
            log.info(
                "node-registry: registered %s (%s)",
                node.node_id,
                node.info.display_name or "unnamed",
            )

        if self.on_node_connect is not None:
            try:
                self.on_node_connect(node.node_id, node.info)
            except Exception:
                log.exception("node-registry: on_node_connect callback error")

    def unregister(self, node_id: str) -> ConnectedNode | None:
        """Remove a disconnected Node."""
        with self._lock:
            node = self._nodes.pop(node_id, None)
            if node is not None:
                log.info("node-registry: unregistered %s", node_id)
                # Clean up pending invokes for this node
                expired = [
                    iid
                    for iid, inv in self._pending_invokes.items()
                    if inv.node_id == node_id
                ]
                for iid in expired:
                    inv = self._pending_invokes.pop(iid)
                    inv.result = {
                        "error": "node_disconnected",
                        "message": f"Node {node_id} disconnected",
                    }
                    inv.event.set()

        if node is not None and self.on_node_disconnect is not None:
            try:
                self.on_node_disconnect(node.node_id, node.info)
            except Exception:
                log.exception("node-registry: on_node_disconnect callback error")

        return node

    def get(self, node_id: str) -> ConnectedNode | None:
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(self) -> list[ConnectedNode]:
        with self._lock:
            return list(self._nodes.values())

    def update_tick(self, node_id: str) -> None:
        """Update Node's last tick time (keepalive)."""
        node = None
        with self._lock:
            node = self._nodes.get(node_id)
            if node is not None:
                node.last_tick_at = time.time()

        if node is not None and self.on_node_tick is not None:
            try:
                self.on_node_tick(node_id)
            except Exception:
                log.exception("node-registry: on_node_tick callback error")

    def invoke(
        self,
        node_id: str,
        command: str,
        args: dict | None = None,
        timeout: float = NODE_INVOKE_TIMEOUT,
    ) -> dict:
        """Send invoke request to Node and synchronously wait for result.

        Reference: OpenClaw node-registry.ts invoke()

        Returns:
            {"ok": True, "data": ...} or {"error": "...", "message": "..."}
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return {
                    "error": "node_not_found",
                    "message": f"Node {node_id} is not connected",
                }

        if command not in DEFAULT_ALLOWED_COMMANDS:
            return {
                "error": "command_not_allowed",
                "message": f"Command {command!r} is not in allowed list",
            }

        invoke_id = str(uuid.uuid4())
        pending = PendingInvoke(
            invoke_id=invoke_id, node_id=node_id, command=command
        )

        with self._lock:
            self._pending_invokes[invoke_id] = pending

        invoke_msg = json.dumps(
            {
                "type": "invoke",
                "invoke_id": invoke_id,
                "command": command,
                "args": args or {},
            }
        )

        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                asyncio.ensure_future, node.ws.send(invoke_msg)
            )
        except Exception as exc:
            with self._lock:
                self._pending_invokes.pop(invoke_id, None)
            return {"error": "send_failed", "message": f"Failed to send invoke: {exc}"}

        log.info(
            "node-invoke: sent %s to %s (id=%s, timeout=%ss)",
            command,
            node_id,
            invoke_id[:8],
            timeout,
        )

        got_result = pending.event.wait(timeout=timeout)

        with self._lock:
            self._pending_invokes.pop(invoke_id, None)

        if not got_result:
            log.warning(
                "node-invoke: timeout for %s on %s (id=%s)",
                command,
                node_id,
                invoke_id[:8],
            )
            return {
                "error": "timeout",
                "message": f"Invoke {command} timed out after {timeout}s",
            }

        return pending.result or {"error": "no_result"}

    def handle_invoke_result(self, invoke_id: str, result: dict) -> bool:
        """Process Node's invoke result reply.

        Returns True if matched, False if invoke_id not found.
        """
        with self._lock:
            pending = self._pending_invokes.get(invoke_id)
            if pending is None:
                log.warning("node-invoke: unknown invoke_id %s", invoke_id[:8])
                return False
            pending.result = result
            pending.event.set()
            log.info(
                "node-invoke: received result for %s (id=%s)",
                pending.command,
                invoke_id[:8],
            )
            return True
