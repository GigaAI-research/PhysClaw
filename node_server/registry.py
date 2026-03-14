from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("physclaw.node_server.registry")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_age_seconds(iso_ts: str) -> float:
    """返回 ISO 时间戳距当前的秒数。"""
    try:
        dt = datetime.fromisoformat(iso_ts)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return float("inf")


class NodeStatus(str, Enum):
    ONLINE = "online"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


@dataclass
class NodeRecord:
    node_id: str
    node_type: str
    endpoint: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.ONLINE
    last_heartbeat: str = field(default_factory=_now_iso)
    registered_at: str = field(default_factory=_now_iso)
    status_changed_at: str = field(default_factory=_now_iso)

    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "endpoint": self.endpoint,
            "metadata": self.metadata,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "registered_at": self.registered_at,
            "status_changed_at": self.status_changed_at,
        }


# 状态变更回调类型: (node_id, old_status, new_status, record)
StatusChangeCallback = Callable[[str, NodeStatus, NodeStatus, NodeRecord], None]


class NodeRegistry:
    def __init__(
        self,
        heartbeat_timeout_sec: int = 30,
        offline_timeout_sec: int = 300,
        store: Optional[Any] = None,
    ) -> None:
        self._nodes: Dict[str, NodeRecord] = {}
        self._lock = threading.Lock()
        self._heartbeat_timeout = heartbeat_timeout_sec
        self._offline_timeout = offline_timeout_sec
        self._on_status_change: List[StatusChangeCallback] = []
        self._store = store  # Optional[NodeStore]

    def on_status_change(self, callback: StatusChangeCallback) -> None:
        """注册状态变更回调。"""
        self._on_status_change.append(callback)

    def _notify_status_change(
        self, node_id: str, old: NodeStatus, new: NodeStatus, record: NodeRecord
    ) -> None:
        for cb in self._on_status_change:
            try:
                cb(node_id, old, new, record)
            except Exception:
                logger.exception("status change callback error for %s", node_id)

    def register(
        self,
        node_id: str,
        node_type: str,
        endpoint: str,
        metadata: Optional[Dict[str, Any]] = None,
        capabilities: Optional[List[str]] = None,
    ) -> NodeRecord:
        now = _now_iso()
        record = NodeRecord(
            node_id=node_id,
            node_type=node_type,
            endpoint=endpoint,
            metadata=dict(metadata or {}),
            capabilities=list(capabilities or []),
            status=NodeStatus.ONLINE,
            last_heartbeat=now,
            registered_at=now,
            status_changed_at=now,
        )
        with self._lock:
            old = self._nodes.get(node_id)
            self._nodes[node_id] = record
        if old and old.status != NodeStatus.ONLINE:
            self._notify_status_change(node_id, old.status, NodeStatus.ONLINE, record)
        if self._store:
            try:
                self._store.save_node(node_id, node_type, endpoint, record.metadata, "online")
            except Exception:
                logger.exception("persist node failed: %s", node_id)
        logger.info("node registered: %s (%s) at %s", node_id, node_type, endpoint)
        return record

    def unregister(self, node_id: str) -> bool:
        with self._lock:
            record = self._nodes.pop(node_id, None)
        if record:
            logger.info("node unregistered: %s", node_id)
            self._notify_status_change(
                node_id, record.status, NodeStatus.OFFLINE, record
            )
            if self._store:
                try:
                    self._store.remove_node(node_id)
                except Exception:
                    logger.exception("persist remove failed: %s", node_id)
        return record is not None

    def heartbeat(self, node_id: str) -> bool:
        now = _now_iso()
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return False
            old_status = node.status
            node.last_heartbeat = now
            if node.status != NodeStatus.ONLINE:
                node.status = NodeStatus.ONLINE
                node.status_changed_at = now
        if old_status != NodeStatus.ONLINE:
            self._notify_status_change(node_id, old_status, NodeStatus.ONLINE, node)
            logger.info("node back online: %s", node_id)
        return True

    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(
        self,
        node_type: Optional[str] = None,
        status: Optional[NodeStatus] = None,
    ) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            result = {}
            for nid, node in self._nodes.items():
                if node_type and node.node_type != node_type:
                    continue
                if status and node.status != status:
                    continue
                result[nid] = node.to_dict()
            return result

    def scan_health(self) -> Dict[str, List[str]]:
        """扫描所有节点，根据心跳超时更新状态。
        返回 {"unhealthy": [...], "removed": [...]}。
        """
        now = _now_iso()
        changes: Dict[str, List[str]] = {"unhealthy": [], "removed": []}
        to_remove: List[str] = []
        status_updates: List[tuple] = []  # (node_id, old, new, record)

        with self._lock:
            for nid, node in list(self._nodes.items()):
                age = _iso_age_seconds(node.last_heartbeat)

                if age >= self._offline_timeout:
                    to_remove.append(nid)
                    changes["removed"].append(nid)
                elif age >= self._heartbeat_timeout and node.status == NodeStatus.ONLINE:
                    old = node.status
                    node.status = NodeStatus.UNHEALTHY
                    node.status_changed_at = now
                    changes["unhealthy"].append(nid)
                    status_updates.append((nid, old, NodeStatus.UNHEALTHY, node))

            for nid in to_remove:
                record = self._nodes.pop(nid)
                status_updates.append((nid, record.status, NodeStatus.OFFLINE, record))

        for nid, old, new, record in status_updates:
            if old != new:
                self._notify_status_change(nid, old, new, record)
                logger.info("health scan: %s %s → %s", nid, old.value, new.value)

        return changes

    def find_by_capability(self, capability: str) -> List[NodeRecord]:
        """查找具有指定能力的在线节点。"""
        with self._lock:
            return [
                n for n in self._nodes.values()
                if n.has_capability(capability) and n.status != NodeStatus.OFFLINE
            ]

    def restore_from_store(self) -> int:
        """从持久化层恢复节点（标记为 offline，等待心跳上线）。"""
        if not self._store:
            return 0
        nodes = self._store.load_all_nodes()
        count = 0
        with self._lock:
            for n in nodes:
                nid = n["node_id"]
                if nid not in self._nodes:
                    self._nodes[nid] = NodeRecord(
                        node_id=nid,
                        node_type=n["node_type"],
                        endpoint=n["endpoint"],
                        metadata=n.get("metadata", {}),
                        status=NodeStatus.OFFLINE,
                        registered_at=n.get("registered_at", _now_iso()),
                        last_heartbeat=_now_iso(),
                    )
                    count += 1
        if count:
            logger.info("restored %d nodes from store (all marked offline)", count)
        return count

    def get_status_summary(self) -> Dict[str, Any]:
        """返回集群状态概览。"""
        with self._lock:
            total = len(self._nodes)
            by_status = {}
            by_type = {}
            for node in self._nodes.values():
                by_status[node.status.value] = by_status.get(node.status.value, 0) + 1
                by_type[node.node_type] = by_type.get(node.node_type, 0) + 1
            return {
                "total_nodes": total,
                "by_status": by_status,
                "by_type": by_type,
            }


class HealthScanner:
    """后台健康扫描器，定期检查节点心跳超时。"""

    def __init__(self, registry: NodeRegistry, interval_sec: int = 10) -> None:
        self._registry = registry
        self._interval = interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="health-scanner")
        self._thread.start()
        logger.info("health scanner started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval + 1)
            self._thread = None
        logger.info("health scanner stopped")

    def _loop(self) -> None:
        while self._running:
            try:
                self._registry.scan_health()
            except Exception:
                logger.exception("health scan error")
            time.sleep(self._interval)
