from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

from node_server.registry import NodeRecord, NodeStatus, NodeRegistry

logger = logging.getLogger("physclaw.node_server.router")


def _http_post(url: str, body: Dict[str, Any], timeout: int = 10) -> Dict[str, Any]:
    """向节点 endpoint POST 消息，返回响应。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return {"ok": True, "status_code": resp.status, "body": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8") if exc.fp else ""
        return {"ok": False, "status_code": exc.code, "error": payload}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "error": str(exc)}


def _is_http_endpoint(endpoint: str) -> bool:
    return endpoint.startswith("http://") or endpoint.startswith("https://")


class MessageRouter:
    def __init__(
        self,
        registry: NodeRegistry,
        delivery_timeout_sec: int = 10,
        delivery_max_retries: int = 3,
        store: Any | None = None,
    ) -> None:
        self.registry = registry
        self._timeout = delivery_timeout_sec
        self._max_retries = delivery_max_retries
        self._store = store  # Optional[NodeStore]

    def _deliver_to_node(self, node: NodeRecord, message: Dict[str, Any]) -> Dict[str, Any]:
        """向单个节点投递消息。HTTP 端点主动 POST，其它返回 dispatch 信息。"""
        if not _is_http_endpoint(node.endpoint):
            return {
                "node_id": node.node_id,
                "delivered": False,
                "reason": "non-http endpoint, dispatch only",
                "endpoint": node.endpoint,
            }

        if node.status == NodeStatus.OFFLINE:
            return {
                "node_id": node.node_id,
                "delivered": False,
                "reason": "node is offline",
            }

        last_error = ""
        for attempt in range(1, self._max_retries + 1):
            url = node.endpoint.rstrip("/") + "/message"
            result = _http_post(url, message, timeout=self._timeout)
            if result["ok"]:
                logger.info("delivered to %s (attempt %d)", node.node_id, attempt)
                self._log_delivery(message, node.node_id, True, attempt)
                return {
                    "node_id": node.node_id,
                    "delivered": True,
                    "attempt": attempt,
                    "response": result.get("body", {}),
                }
            last_error = result.get("error", "unknown")
            logger.warning(
                "delivery failed to %s (attempt %d/%d): %s",
                node.node_id, attempt, self._max_retries, last_error,
            )
            if attempt < self._max_retries:
                time.sleep(min(2 ** (attempt - 1), 8))  # 1s, 2s, 4s... 最大 8s

        self._log_delivery(message, node.node_id, False, self._max_retries, last_error)
        return {
            "node_id": node.node_id,
            "delivered": False,
            "reason": f"max retries exceeded: {last_error}",
            "attempts": self._max_retries,
        }

    def _log_delivery(
        self, message: Dict[str, Any], target: str, delivered: bool,
        attempts: int = 1, error: str = "",
    ) -> None:
        if not self._store:
            return
        try:
            self._store.log_delivery(
                message_id=str(message.get("message_id", "")),
                source=str(message.get("source", "")),
                target=target,
                action=str(message.get("action", "")),
                delivered=delivered,
                attempts=attempts,
                error=error,
            )
        except Exception:
            logger.exception("log delivery failed")

    def route(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """直接路由：投递到指定 target 节点。"""
        target_id = str(message.get("target") or "")
        if not target_id:
            return {"ok": False, "error": "target is required"}
        node = self.registry.get_node(target_id)
        if node is None:
            return {"ok": False, "error": f"target node not found: {target_id}"}

        delivery = self._deliver_to_node(node, message)
        return {
            "ok": True,
            "mode": "direct",
            "target": node.to_dict(),
            "delivery": delivery,
        }

    def broadcast(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """广播：投递到所有在线/unhealthy 节点。"""
        nodes = self._get_deliverable_nodes()
        deliveries = [self._deliver_to_node(n, message) for n in nodes]
        return {
            "ok": True,
            "mode": "broadcast",
            "total": len(nodes),
            "deliveries": deliveries,
        }

    def route_to_type(self, node_type: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """按类型路由：投递到指定类型的所有节点。"""
        nodes = self._get_deliverable_nodes(node_type=node_type)
        if not nodes:
            return {"ok": False, "error": f"no nodes of type: {node_type}"}
        deliveries = [self._deliver_to_node(n, message) for n in nodes]
        return {
            "ok": True,
            "mode": "type",
            "node_type": node_type,
            "total": len(nodes),
            "deliveries": deliveries,
        }

    def route_to_capability(self, capability: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """按能力路由：投递到具有指定能力的节点。"""
        nodes = self.registry.find_by_capability(capability)
        if not nodes:
            return {"ok": False, "error": f"no nodes with capability: {capability}"}
        deliveries = [self._deliver_to_node(n, message) for n in nodes]
        return {
            "ok": True,
            "mode": "capability",
            "capability": capability,
            "total": len(nodes),
            "deliveries": deliveries,
        }

    def _get_deliverable_nodes(self, node_type: str | None = None) -> List[NodeRecord]:
        """获取可投递的节点列表（排除 OFFLINE）。"""
        with self.registry._lock:
            return [
                n for n in self.registry._nodes.values()
                if n.status != NodeStatus.OFFLINE
                and (node_type is None or n.node_type == node_type)
            ]
