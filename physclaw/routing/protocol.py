"""JSON-RPC 2.0 protocol helpers.

Reference: OpenClaw s05_gateway.py JSON-RPC constants and helpers
"""

from __future__ import annotations

import json
from typing import Any

JSONRPC_VERSION = "2.0"

# Error codes (JSON-RPC 2.0 spec)
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
AUTH_ERROR = -32000


def make_result(req_id: str | int | None, result: Any) -> str:
    """Build JSON-RPC 2.0 success response."""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "result": result,
    })


def make_error(req_id: str | int | None, code: int, message: str) -> str:
    """Build JSON-RPC 2.0 error response."""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "error": {"code": code, "message": message},
    })


def make_event(event_type: str, payload: dict[str, Any]) -> str:
    """Build JSON-RPC 2.0 event notification (server push)."""
    return json.dumps({
        "jsonrpc": JSONRPC_VERSION,
        "method": "event",
        "params": {"type": event_type, **payload},
    })
