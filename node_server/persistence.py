"""SQLite 轻量持久化层：节点注册信息 + 消息投递日志。"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("physclaw.node_server.persistence")

_DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), ".physclaw")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "node_server.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT PRIMARY KEY,
    node_type   TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'offline',
    registered_at TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT,
    source      TEXT,
    target      TEXT,
    action      TEXT,
    delivered   INTEGER NOT NULL DEFAULT 0,
    attempts    INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_delivery_target ON delivery_log(target);
CREATE INDEX IF NOT EXISTS idx_delivery_created ON delivery_log(created_at);
"""


class NodeStore:
    """线程安全的 SQLite 节点持久化存储。"""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or os.getenv("PHYSCLAW_DB_PATH", _DEFAULT_DB_PATH)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()
        logger.info("database initialized: %s", self._db_path)

    # ── 节点操作 ──

    def save_node(
        self,
        node_id: str,
        node_type: str,
        endpoint: str,
        metadata: Dict[str, Any],
        status: str = "online",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO nodes (node_id, node_type, endpoint, metadata, status, registered_at, last_heartbeat)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                   node_type=excluded.node_type,
                   endpoint=excluded.endpoint,
                   metadata=excluded.metadata,
                   status=excluded.status,
                   last_heartbeat=excluded.last_heartbeat
            """,
            (node_id, node_type, endpoint, json.dumps(metadata), status, now, now),
        )
        conn.commit()

    def remove_node(self, node_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
        conn.commit()

    def update_node_status(self, node_id: str, status: str) -> None:
        conn = self._get_conn()
        conn.execute("UPDATE nodes SET status = ? WHERE node_id = ?", (status, node_id))
        conn.commit()

    def load_all_nodes(self) -> List[Dict[str, Any]]:
        """加载所有持久化的节点（重启恢复用，全部标记为 offline）。"""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM nodes").fetchall()
        result = []
        for row in rows:
            result.append({
                "node_id": row["node_id"],
                "node_type": row["node_type"],
                "endpoint": row["endpoint"],
                "metadata": json.loads(row["metadata"]),
                "status": "offline",  # 重启后一律 offline，等心跳恢复
                "registered_at": row["registered_at"],
            })
        return result

    # ── 投递日志 ──

    def log_delivery(
        self,
        message_id: str,
        source: str,
        target: str,
        action: str,
        delivered: bool,
        attempts: int = 1,
        error: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO delivery_log (message_id, source, target, action, delivered, attempts, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, source, target, action, int(delivered), attempts, error, now),
        )
        conn.commit()

    def get_delivery_logs(
        self,
        target: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if target:
            rows = conn.execute(
                "SELECT * FROM delivery_log WHERE target = ? ORDER BY created_at DESC LIMIT ?",
                (target, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM delivery_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
