"""Node agent tools: node_list, node_invoke.

Allows the Agent to interact with connected remote devices.

Reference: OpenClaw src/agents/tools/nodes-tool.ts
"""

from __future__ import annotations

import json
import time

from nanobot.engine.tools.registry import ToolRegistry
from nanobot.node.registry import NodeRegistry

NODE_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "node_invoke",
        "description": (
            "Invoke a command on a connected remote node (device). "
            "Use this to run commands on phones, computers, or other devices. "
            "Available commands: system.run, system.notify, camera.snap, "
            "location.get, screen.snap"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "The node_id of the target device",
                },
                "command": {
                    "type": "string",
                    "description": (
                        "Command to execute. One of: system.run, "
                        "system.notify, camera.snap, location.get, screen.snap"
                    ),
                },
                "args": {
                    "type": "object",
                    "description": (
                        'Command arguments (e.g. {"cmd": "ls -la"} for system.run)'
                    ),
                },
            },
            "required": ["node_id", "command"],
        },
    },
}

NODE_LIST_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "node_list",
        "description": (
            "List all connected remote nodes (devices). "
            "Shows node_id, display_name, platform, capabilities."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def execute_node_tool(
    tool_name: str,
    args: dict,
    registry: NodeRegistry,
) -> str:
    """Execute a node tool call, return JSON string result."""
    if tool_name == "node_list":
        nodes = registry.list_nodes()
        if not nodes:
            return json.dumps({"nodes": [], "message": "No nodes connected"})
        result = []
        for n in nodes:
            result.append(
                {
                    "node_id": n.node_id,
                    "display_name": n.info.display_name,
                    "platform": n.info.platform,
                    "caps": n.info.caps,
                    "connected_seconds": int(time.time() - n.connected_at),
                }
            )
        return json.dumps({"nodes": result})

    elif tool_name == "node_invoke":
        node_id = args.get("node_id", "")
        command = args.get("command", "")
        invoke_args = args.get("args", {})
        if not node_id:
            return json.dumps({"error": "node_id required"})
        if not command:
            return json.dumps({"error": "command required"})
        result = registry.invoke(node_id, command, invoke_args)
        return json.dumps(result)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def build_node_tool_registry(node_registry: NodeRegistry) -> ToolRegistry:
    """Create a ToolRegistry for Node tools.

    Usage (composing full tool set):
        base_reg = build_soul_memory_registry(agent)
        node_reg = build_node_tool_registry(registry)
        all_tools = base_reg.merge(node_reg)
    """
    reg = ToolRegistry()
    reg.register(
        "node_list",
        NODE_LIST_TOOL_SPEC,
        lambda **_kwargs: execute_node_tool("node_list", {}, node_registry),
    )
    reg.register(
        "node_invoke",
        NODE_TOOL_SPEC,
        lambda **kwargs: execute_node_tool("node_invoke", kwargs, node_registry),
    )
    return reg
