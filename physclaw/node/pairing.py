"""NodePairingStore: persistent pairing lifecycle.

Manages device-to-gateway trust establishment:
  1. Node sends pairing request → stored as "pending"
  2. User approves on Gateway side → "approved" (paired)
  3. Approval generates token → Node uses it for future auth
  4. On connect, Gateway verifies token → registers to NodeRegistry

Reference: OpenClaw src/infra/node-pairing.ts
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from pathlib import Path

from nanobot.node.info import NodeInfo

log = logging.getLogger(__name__)

# Pending request TTL (5 minutes)
# Reference: OpenClaw PENDING_TTL_MS = 5 * 60 * 1000
PENDING_TTL_S = 5 * 60


class NodePairingStore:
    """Persistent storage for node pairing information.

    Reference: OpenClaw src/infra/node-pairing.ts loadState / persistState

    Manages two states:
      - pending: pairing requests awaiting approval (with TTL)
      - paired:  approved devices (persistent)
    """

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not self.store_path.exists():
            return {"pending": {}, "paired": {}}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            if "pending" not in data:
                data["pending"] = {}
            if "paired" not in data:
                data["paired"] = {}
            return data
        except (json.JSONDecodeError, OSError):
            return {"pending": {}, "paired": {}}

    def _save(self, data: dict) -> None:
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self.store_path)

    def _prune_expired(self, data: dict) -> None:
        """Remove expired pending requests."""
        now = time.time()
        expired = [
            rid
            for rid, req in data["pending"].items()
            if now - req.get("ts", 0) > PENDING_TTL_S
        ]
        for rid in expired:
            del data["pending"][rid]

    def request_pairing(self, info: NodeInfo) -> dict:
        """Node initiates a pairing request.

        Reference: OpenClaw requestNodePairing()
        """
        data = self._load()
        self._prune_expired(data)

        node_id = info.node_id.strip()
        if not node_id:
            raise ValueError("node_id required")

        # Reuse existing pending request for same node_id
        for rid, req in data["pending"].items():
            if req.get("node_id") == node_id:
                req.update(
                    {
                        "display_name": info.display_name,
                        "platform": info.platform,
                        "version": info.version,
                        "caps": info.caps,
                        "commands": info.commands,
                        "ts": time.time(),
                    }
                )
                self._save(data)
                return {"status": "pending", "request_id": rid, "created": False}

        is_repair = node_id in data["paired"]
        request_id = str(uuid.uuid4())
        data["pending"][request_id] = {
            "request_id": request_id,
            "node_id": node_id,
            "display_name": info.display_name,
            "platform": info.platform,
            "version": info.version,
            "caps": info.caps,
            "commands": info.commands,
            "permissions": info.permissions,
            "is_repair": is_repair,
            "ts": time.time(),
        }
        self._save(data)
        log.info(
            "pairing: created pending request %s for node %s (repair=%s)",
            request_id,
            node_id,
            is_repair,
        )
        return {"status": "pending", "request_id": request_id, "created": True}

    def approve(self, request_id: str) -> dict | None:
        """Approve a pairing request → generate token → store as paired.

        Reference: OpenClaw approveNodePairing()
        """
        data = self._load()
        self._prune_expired(data)

        pending = data["pending"].get(request_id)
        if pending is None:
            return None

        node_id = pending["node_id"]
        token = secrets.token_urlsafe(32)
        now = time.time()

        existing = data["paired"].get(node_id)
        created_at = existing.get("paired_at", now) if existing else now

        paired_node = {
            "node_id": node_id,
            "token": token,
            "display_name": pending.get("display_name", ""),
            "platform": pending.get("platform", ""),
            "version": pending.get("version", ""),
            "caps": pending.get("caps", []),
            "commands": pending.get("commands", []),
            "permissions": pending.get("permissions", {}),
            "paired_at": created_at,
            "approved_at": now,
        }

        del data["pending"][request_id]
        data["paired"][node_id] = paired_node
        self._save(data)
        log.info("pairing: approved request %s -> node %s", request_id, node_id)
        return {"request_id": request_id, "node": paired_node}

    def reject(self, request_id: str) -> dict | None:
        """Reject a pairing request."""
        data = self._load()
        pending = data["pending"].get(request_id)
        if pending is None:
            return None
        node_id = pending["node_id"]
        del data["pending"][request_id]
        self._save(data)
        return {"request_id": request_id, "node_id": node_id}

    def verify_token(self, node_id: str, token: str) -> dict | None:
        """Verify a Node's connection token.

        Reference: OpenClaw verifyNodeToken()
        Uses constant-time comparison to prevent timing attacks.
        """
        data = self._load()
        node_id = node_id.strip()
        paired = data["paired"].get(node_id)
        if paired is None:
            return None
        stored_token = paired.get("token", "")
        if not secrets.compare_digest(stored_token, token):
            return None
        return paired

    def list_pairing(self) -> dict:
        """List all pending and paired nodes."""
        data = self._load()
        self._prune_expired(data)
        pending = sorted(
            data["pending"].values(), key=lambda r: r.get("ts", 0), reverse=True
        )
        paired = sorted(
            data["paired"].values(),
            key=lambda n: n.get("approved_at", 0),
            reverse=True,
        )
        return {"pending": pending, "paired": paired}

    def rename_node(self, node_id: str, display_name: str) -> dict | None:
        """Rename a paired node."""
        data = self._load()
        node_id = node_id.strip()
        paired = data["paired"].get(node_id)
        if paired is None:
            return None
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("display_name required")
        paired["display_name"] = display_name
        self._save(data)
        return paired

    def update_metadata(self, node_id: str, patch: dict) -> None:
        """Update paired node metadata (refresh version/caps on connect)."""
        data = self._load()
        node_id = node_id.strip()
        paired = data["paired"].get(node_id)
        if paired is None:
            return
        for key in (
            "display_name",
            "platform",
            "version",
            "caps",
            "commands",
            "permissions",
        ):
            if key in patch and patch[key] is not None:
                paired[key] = patch[key]
        if "last_connected_at" in patch:
            paired["last_connected_at"] = patch["last_connected_at"]
        self._save(data)
