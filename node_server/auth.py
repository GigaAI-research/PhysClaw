"""简单的 Token 认证模块。

节点注册时颁发 node_token，后续请求须携带。
管理端点使用独立的 admin_token。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
from typing import Dict, Optional, Tuple

logger = logging.getLogger("physclaw.node_server.auth")

# 管理员 token，从环境变量读取或自动生成
_ADMIN_TOKEN = os.getenv("PHYSCLAW_ADMIN_TOKEN", "")


def get_admin_token() -> str:
    global _ADMIN_TOKEN
    if not _ADMIN_TOKEN:
        _ADMIN_TOKEN = secrets.token_hex(32)
        logger.info("auto-generated admin token: %s", _ADMIN_TOKEN)
    return _ADMIN_TOKEN


class TokenManager:
    """管理节点 token 的颁发与验证。"""

    def __init__(self) -> None:
        self._tokens: Dict[str, str] = {}  # node_id → token_hash
        self._lock = threading.Lock()

    def issue_token(self, node_id: str) -> str:
        """为节点颁发新 token。"""
        token = secrets.token_hex(24)
        token_hash = self._hash(token)
        with self._lock:
            self._tokens[node_id] = token_hash
        return token

    def verify_node_token(self, node_id: str, token: str) -> bool:
        """验证节点 token（constant-time 比较）。"""
        with self._lock:
            expected = self._tokens.get(node_id)
        if expected is None:
            return False
        return hmac.compare_digest(expected, self._hash(token))

    def revoke(self, node_id: str) -> None:
        with self._lock:
            self._tokens.pop(node_id, None)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


def verify_admin_token(token: str) -> bool:
    """验证管理员 token。"""
    expected = get_admin_token()
    return hmac.compare_digest(expected, token)


def extract_token(headers: dict) -> Tuple[Optional[str], Optional[str]]:
    """从请求头提取认证信息。
    支持:
      Authorization: Bearer <token>
      X-Node-Id: <node_id>
      X-Node-Token: <token>
      X-Admin-Token: <token>
    返回 (node_token_or_admin_token, token_type)
    token_type: "node" | "admin" | None
    """
    # 管理员 token
    admin = headers.get("X-Admin-Token", "")
    if admin:
        return admin, "admin"

    # 节点 token
    node_token = headers.get("X-Node-Token", "")
    if node_token:
        return node_token, "node"

    # Bearer token（通用）
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip(), "bearer"

    return None, None
