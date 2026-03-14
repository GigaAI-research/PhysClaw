"""Node: cross-device lightweight client agents.

Provides remote device management through WebSocket connections:
- NodeInfo: device description (platform, capabilities, commands)
- NodePairingStore: pairing lifecycle (request → approve → verify)
- NodeRegistry: runtime registry of connected nodes
- NodeClient: WebSocket client with auto-reconnect + heartbeat tick
- NodeEventSource: bridges node lifecycle events for external consumers
- Node tools: node_list, node_invoke for agent tool calling

Reference: OpenClaw src/infra/node-pairing.ts, src/gateway/node-registry.ts
"""

from nanobot.node.info import (
    NodeInfo,
    NODE_CMD_SYSTEM_RUN,
    NODE_CMD_SYSTEM_NOTIFY,
    NODE_CMD_SYSTEM_WHICH,
    NODE_CMD_CAMERA_SNAP,
    NODE_CMD_LOCATION,
    NODE_CMD_SCREEN_SNAP,
    DEFAULT_ALLOWED_COMMANDS,
)
from nanobot.node.pairing import NodePairingStore, PENDING_TTL_S
from nanobot.node.registry import (
    NodeRegistry,
    ConnectedNode,
    PendingInvoke,
    NODE_INVOKE_TIMEOUT,
)
from nanobot.node.events import NodeEventSource, handle_node_event
from nanobot.node.client import NodeClient, SimulatedNodeHandler
from nanobot.node.tools import (
    NODE_TOOL_SPEC,
    NODE_LIST_TOOL_SPEC,
    execute_node_tool,
    build_node_tool_registry,
)

__all__ = [
    "NodeInfo",
    "NODE_CMD_SYSTEM_RUN",
    "NODE_CMD_SYSTEM_NOTIFY",
    "NODE_CMD_SYSTEM_WHICH",
    "NODE_CMD_CAMERA_SNAP",
    "NODE_CMD_LOCATION",
    "NODE_CMD_SCREEN_SNAP",
    "DEFAULT_ALLOWED_COMMANDS",
    "NodePairingStore",
    "PENDING_TTL_S",
    "NodeRegistry",
    "ConnectedNode",
    "PendingInvoke",
    "NODE_INVOKE_TIMEOUT",
    "NodeEventSource",
    "handle_node_event",
    "NodeClient",
    "SimulatedNodeHandler",
    "NODE_TOOL_SPEC",
    "NODE_LIST_TOOL_SPEC",
    "execute_node_tool",
    "build_node_tool_registry",
]
