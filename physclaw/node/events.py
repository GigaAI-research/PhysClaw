"""Node event handling and NodeEventSource.

NodeEventSource bridges NodeRegistry lifecycle events for external consumers.
handle_node_event processes events from Node devices.

Reference: OpenClaw src/gateway/server-node-events.ts
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from nanobot.node.info import NodeInfo
from nanobot.node.registry import NodeRegistry

log = logging.getLogger(__name__)


class NodeEventSource:
    """Bridges NodeRegistry lifecycle events to external consumers.

    This is a passive event source — no background thread. It hooks into
    NodeRegistry callbacks and emits events when nodes connect/disconnect/tick.
    """

    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry
        self.name: str = "node"
        self._emit_callback: Callable | None = None
        self._started: bool = False
        self._total_emitted: int = 0

        # Install callbacks
        registry.on_node_connect = self._on_connect
        registry.on_node_disconnect = self._on_disconnect
        registry.on_node_tick = self._on_tick
        registry.on_node_event = self._on_event

    def _emit(self, event: dict) -> None:
        if self._emit_callback:
            self._emit_callback(event)
            self._total_emitted += 1

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False
        self._registry.on_node_connect = None
        self._registry.on_node_disconnect = None
        self._registry.on_node_tick = None
        self._registry.on_node_event = None

    def status(self) -> dict:
        online = self._registry.list_nodes()
        return {
            "name": self.name,
            "started": self._started,
            "total_emitted": self._total_emitted,
            "online_nodes": len(online),
            "online_node_ids": [n.node_id for n in online],
        }

    def _on_connect(self, node_id: str, info: NodeInfo) -> None:
        if not self._started:
            return
        self._emit(
            {
                "source": "node",
                "type": "node.connected",
                "payload": {
                    "node_id": node_id,
                    "display_name": info.display_name or "",
                    "platform": info.platform,
                    "caps": info.caps,
                },
                "timestamp": time.time(),
            }
        )

    def _on_disconnect(self, node_id: str, info: NodeInfo) -> None:
        if not self._started:
            return
        self._emit(
            {
                "source": "node",
                "type": "node.disconnected",
                "payload": {
                    "node_id": node_id,
                    "display_name": info.display_name or "",
                    "platform": info.platform,
                },
                "timestamp": time.time(),
            }
        )

    def _on_tick(self, node_id: str) -> None:
        if not self._started:
            return
        self._emit(
            {
                "source": "node",
                "type": "node.tick",
                "payload": {"node_id": node_id},
                "timestamp": time.time(),
            }
        )

    def _on_event(self, node_id: str, event: str, payload: dict) -> None:
        if not self._started:
            return
        self._emit(
            {
                "source": "node",
                "type": "node.event",
                "payload": {"node_id": node_id, "event": event, **payload},
                "timestamp": time.time(),
            }
        )


def handle_node_event(node_id: str, event: str, payload: dict) -> str | None:
    """Process a Node event and return broadcast text (or None).

    Reference: OpenClaw handleNodeEvent()
    """
    if event == "exec.started":
        command = payload.get("command", "")
        run_id = payload.get("run_id", "")
        text = f"Exec started (node={node_id}"
        if run_id:
            text += f" id={run_id}"
        text += ")"
        if command:
            text += f": {command}"
        return text

    elif event == "exec.finished":
        exit_code = payload.get("exit_code")
        timed_out = payload.get("timed_out", False)
        output = (payload.get("output") or "").strip()
        run_id = payload.get("run_id", "")
        exit_label = "timeout" if timed_out else f"code {exit_code}"

        if not timed_out and exit_code == 0 and not output:
            return None

        text = f"Exec finished (node={node_id}"
        if run_id:
            text += f" id={run_id}"
        text += f", {exit_label})"

        if output:
            compact = output.replace("\n", " ").strip()
            if len(compact) > 180:
                compact = compact[:179] + "\u2026"
            if compact:
                text += f"\n{compact}"
        return text

    elif event == "exec.denied":
        command = payload.get("command", "")
        reason = payload.get("reason", "")
        run_id = payload.get("run_id", "")
        text = f"Exec denied (node={node_id}"
        if run_id:
            text += f" id={run_id}"
        if reason:
            text += f", {reason}"
        text += ")"
        if command:
            text += f": {command}"
        return text

    elif event == "notifications.changed":
        change = (payload.get("change") or "").lower()
        if change not in ("posted", "removed"):
            return None
        key = payload.get("key", "")
        package = payload.get("package_name", "")
        title = (payload.get("title") or "").strip()[:120]
        body = (payload.get("text") or "").strip()[:120]
        text = f"Notification {change} (node={node_id} key={key}"
        if package:
            text += f" package={package}"
        text += ")"
        if change == "posted":
            parts = [p for p in [title, body] if p]
            if parts:
                text += f": {' - '.join(parts)}"
        return text

    elif event == "voice.transcript":
        transcript = (payload.get("text") or "").strip()
        if transcript:
            return f"Voice transcript (node={node_id}): {transcript[:120]}"
        return None

    return None
