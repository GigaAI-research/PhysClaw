"""Routing, configuration, and WebSocket gateway.

Provides AgentConfig, Binding, MessageRouter, RoutingGateway, and JSON-RPC protocol.
"""

from nanobot.routing.config import AgentConfig, Binding, load_routing_config, DEFAULT_CONFIG
from nanobot.routing.router import MessageRouter, build_session_key
from nanobot.routing.server import RoutingGateway, ConnectedClient
from nanobot.routing.protocol import (
    JSONRPC_VERSION,
    PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND,
    INTERNAL_ERROR, AUTH_ERROR,
    make_result, make_error, make_event,
)

__all__ = [
    "AgentConfig", "Binding", "load_routing_config", "DEFAULT_CONFIG",
    "MessageRouter", "build_session_key",
    "RoutingGateway", "ConnectedClient",
    "JSONRPC_VERSION", "PARSE_ERROR", "INVALID_REQUEST",
    "METHOD_NOT_FOUND", "INTERNAL_ERROR", "AUTH_ERROR",
    "make_result", "make_error", "make_event",
]
