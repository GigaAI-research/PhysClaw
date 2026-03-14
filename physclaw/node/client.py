"""NodeClient: WebSocket client with auto-reconnect + heartbeat tick.

NodeClient runs on the device side, connecting to the Gateway.
Features:
  - Auto-reconnect with exponential backoff (1s → 2s → 4s → ... → 60s)
  - Heartbeat tick (keepalive)
  - Invoke handling (receive and execute Gateway commands)
  - Event sending (notify Gateway of device state changes)

Reference: OpenClaw src/gateway/client.ts GatewayClient
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

from nanobot.node.info import (
    NodeInfo,
    NODE_CMD_SYSTEM_RUN,
    NODE_CMD_SYSTEM_NOTIFY,
    NODE_CMD_CAMERA_SNAP,
    NODE_CMD_LOCATION,
    NODE_CMD_SCREEN_SNAP,
)

log = logging.getLogger(__name__)

# Heartbeat tick interval (seconds)
NODE_TICK_INTERVAL = 30

# Reconnect backoff parameters
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0
RECONNECT_MULTIPLIER = 2.0


class SimulatedNodeHandler:
    """Simulated Node invoke handler for local testing."""

    def __init__(self, node_id: str, platform: str = "simulated") -> None:
        self.node_id = node_id
        self.platform = platform

    def handle_invoke(self, invoke_id: str, command: str, args: dict) -> dict:
        if command == NODE_CMD_SYSTEM_RUN:
            cmd = args.get("cmd", "echo hello")
            return {
                "ok": True,
                "data": {
                    "exit_code": 0,
                    "stdout": f"[simulated] output of: {cmd}",
                    "stderr": "",
                },
            }
        elif command == NODE_CMD_SYSTEM_NOTIFY:
            return {"ok": True, "data": {"sent": True}}
        elif command == NODE_CMD_CAMERA_SNAP:
            return {
                "ok": True,
                "data": {
                    "format": "jpeg",
                    "size": 12345,
                    "message": "[simulated] camera snap taken",
                },
            }
        elif command == NODE_CMD_LOCATION:
            return {
                "ok": True,
                "data": {
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "accuracy": 10.0,
                    "message": "[simulated] Beijing, China",
                },
            }
        elif command == NODE_CMD_SCREEN_SNAP:
            return {
                "ok": True,
                "data": {
                    "format": "png",
                    "size": 67890,
                    "message": "[simulated] screen snap taken",
                },
            }
        else:
            return {
                "error": "unsupported_command",
                "message": f"Command {command} not supported",
            }


class NodeClient:
    """Device-side WebSocket client connecting to Gateway.

    Reference: OpenClaw src/gateway/client.ts GatewayClient
    """

    def __init__(
        self,
        gateway_url: str,
        node_id: str,
        token: str,
        info: NodeInfo | None = None,
        *,
        tick_interval: float = NODE_TICK_INTERVAL,
        on_invoke: Callable[[str, str, dict], dict] | None = None,
    ) -> None:
        self.gateway_url = gateway_url
        self.node_id = node_id
        self.token = token
        self.info = info or NodeInfo(node_id=node_id)
        self.tick_interval = tick_interval
        self.on_invoke = on_invoke

        self._ws = None
        self._connected = False
        self._reconnect_count = 0
        self._should_run = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start client — connect to Gateway and maintain connection."""
        self._should_run = True
        while self._should_run:
            try:
                await self._connect_and_run()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._should_run:
                    break
                delay = self._next_reconnect_delay()
                log.warning(
                    "node-client: connection lost (%s), "
                    "reconnecting in %.1fs (attempt #%d)",
                    exc,
                    delay,
                    self._reconnect_count,
                )
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        self._should_run = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._connected = False

    async def send_event(self, event: str, payload: dict | None = None) -> None:
        """Send event to Gateway."""
        if self._ws is None or not self._connected:
            return
        msg = json.dumps(
            {"type": "node.event", "event": event, "payload": payload or {}}
        )
        try:
            await self._ws.send(msg)
        except Exception as exc:
            log.warning("node-client: failed to send event %s: %s", event, exc)

    def _next_reconnect_delay(self) -> float:
        self._reconnect_count += 1
        delay = RECONNECT_BASE_DELAY * (
            RECONNECT_MULTIPLIER ** (self._reconnect_count - 1)
        )
        return min(delay, RECONNECT_MAX_DELAY)

    async def _connect_and_run(self) -> None:
        try:
            import websockets
        except ImportError:
            log.error("node-client: websockets package required")
            raise

        async with websockets.connect(self.gateway_url) as ws:
            self._ws = ws
            self._connected = True
            self._reconnect_count = 0

            auth_msg = json.dumps(
                {
                    "type": "node.auth",
                    "node_id": self.node_id,
                    "token": self.token,
                    "info": self.info.to_dict(),
                }
            )
            await ws.send(auth_msg)

            tick_task = asyncio.create_task(self._tick_loop(ws))
            try:
                async for raw in ws:
                    await self._handle_message(ws, raw)
            finally:
                tick_task.cancel()
                self._connected = False
                self._ws = None

    async def _tick_loop(self, ws) -> None:
        while True:
            await asyncio.sleep(self.tick_interval)
            try:
                tick_msg = json.dumps(
                    {"type": "node.tick", "node_id": self.node_id, "ts": time.time()}
                )
                await ws.send(tick_msg)
            except Exception:
                break

    async def _handle_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == "invoke":
            invoke_id = msg.get("invoke_id", "")
            command = msg.get("command", "")
            args = msg.get("args", {})

            if self.on_invoke is not None:
                try:
                    result = self.on_invoke(invoke_id, command, args)
                except Exception as exc:
                    result = {"error": "handler_error", "message": str(exc)}
            else:
                result = {"error": "no_handler", "message": "No invoke handler"}

            result_msg = json.dumps(
                {"type": "invoke.result", "invoke_id": invoke_id, "result": result}
            )
            try:
                await ws.send(result_msg)
            except Exception:
                pass

        elif msg_type == "auth.ok":
            log.info("node-client: auth successful")
        elif msg_type == "auth.failed":
            reason = msg.get("reason", "unknown")
            log.error("node-client: auth failed: %s", reason)
            self._should_run = False
