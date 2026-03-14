from __future__ import annotations

import json
import logging
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from node_server.auth import TokenManager, extract_token, get_admin_token, verify_admin_token
from node_server.config import get_server_runtime_config
from node_server.message_protocol import validate_message
from node_server.persistence import NodeStore
from node_server.registry import HealthScanner, NodeRegistry, NodeStatus
from node_server.router import MessageRouter

logger = logging.getLogger("physclaw.node_server")

# 匹配 /nodes/<node_id> 路径
_NODE_DETAIL_RE = re.compile(r"^/nodes/([^/]+)$")


class PhysClawNodeServer:
	def __init__(self) -> None:
		self.config = get_server_runtime_config()
		self.store = NodeStore()
		self.registry = NodeRegistry(
			heartbeat_timeout_sec=self.config.heartbeat_timeout_sec,
			offline_timeout_sec=self.config.offline_timeout_sec,
			store=self.store,
		)
		self.router = MessageRouter(
			self.registry,
			delivery_timeout_sec=self.config.delivery_timeout_sec,
			delivery_max_retries=self.config.delivery_max_retries,
			store=self.store,
		)
		self.health_scanner = HealthScanner(
			self.registry,
			interval_sec=self.config.health_scan_interval_sec,
		)

		self.token_manager = TokenManager()

		# 注册状态变更日志
		self.registry.on_status_change(self._log_status_change)

		# 从持久化恢复节点
		self.registry.restore_from_store()

	@staticmethod
	def _log_status_change(node_id: str, old: NodeStatus, new: NodeStatus, record: Any) -> None:
		logger.info("[status] %s: %s → %s", node_id, old.value, new.value)

	def create_handler(self):
		server = self

		class Handler(BaseHTTPRequestHandler):
			def _read_json(self) -> Dict[str, Any]:
				length = int(self.headers.get("Content-Length", "0"))
				raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
				try:
					return json.loads(raw)
				except Exception:
					return {}

			def _write_json(self, code: int, payload: Dict[str, Any]) -> None:
				body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
				self.send_response(code)
				self.send_header("Content-Type", "application/json; charset=utf-8")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.write(body)

			def log_message(self, format: str, *args: Any) -> None:
				logger.debug(format, *args)

			def _check_node_auth(self, node_id: str) -> bool:
				"""验证节点请求的 token。无 token 机制时放行（向后兼容）。"""
				token = self.headers.get("X-Node-Token", "")
				if not token:
					return True  # 未携带 token 时放行（兼容旧节点）
				return server.token_manager.verify_node_token(node_id, token)

			def _check_admin_auth(self) -> bool:
				"""验证管理端点的 admin token。"""
				token = self.headers.get("X-Admin-Token", "")
				if not token:
					return True  # 未配置时放行
				return verify_admin_token(token)

			def do_GET(self) -> None:
				parsed = urlparse(self.path)
				path = parsed.path.rstrip("/") or "/"

				# GET /health
				if path == "/health":
					summary = server.registry.get_status_summary()
					self._write_json(200, {
						"ok": True,
						"service": "physclaw-node-server",
						**summary,
					})
					return

				# GET /status — 集群状态概览
				if path == "/status":
					summary = server.registry.get_status_summary()
					nodes = server.registry.list_nodes()
					self._write_json(200, {
						"ok": True,
						**summary,
						"nodes": nodes,
					})
					return

				# GET /nodes?type=<optional>&status=<optional>
				if path == "/nodes":
					qs = parse_qs(parsed.query)
					node_type = qs.get("type", [None])[0]
					status_str = qs.get("status", [None])[0]
					status = None
					if status_str:
						try:
							status = NodeStatus(status_str)
						except ValueError:
							self._write_json(400, {"ok": False, "error": f"invalid status: {status_str}"})
							return
					data = server.registry.list_nodes(node_type=node_type, status=status)
					self._write_json(200, {"ok": True, "nodes": data})
					return

				# GET /nodes/<node_id>
				m = _NODE_DETAIL_RE.match(path)
				if m:
					node_id = m.group(1)
					node = server.registry.get_node(node_id)
					if node is None:
						self._write_json(404, {"ok": False, "error": f"node not found: {node_id}"})
						return
					self._write_json(200, {"ok": True, "node": node.to_dict()})
					return

				# GET /logs?target=<optional>&limit=<optional>
				if path == "/logs":
					qs = parse_qs(parsed.query)
					target = qs.get("target", [None])[0]
					limit = int(qs.get("limit", ["100"])[0])
					logs = server.store.get_delivery_logs(target=target, limit=limit)
					self._write_json(200, {"ok": True, "logs": logs})
					return

				self._write_json(404, {"ok": False, "error": "not found"})

			def do_POST(self) -> None:
				parsed = urlparse(self.path)
				path = parsed.path.rstrip("/") or "/"

				# POST /register
				if path == "/register":
					body = self._read_json()
					required = ("node_id", "node_type", "endpoint")
					missing = [k for k in required if not body.get(k)]
					if missing:
						self._write_json(400, {"ok": False, "error": f"missing fields: {missing}"})
						return
					node_id = str(body["node_id"])
					record = server.registry.register(
						node_id=node_id,
						node_type=str(body["node_type"]),
						endpoint=str(body["endpoint"]),
						metadata=dict(body.get("metadata") or {}),
						capabilities=list(body.get("capabilities") or []),
					)
					# 颁发 node_token
					token = server.token_manager.issue_token(node_id)
					self._write_json(200, {
						"ok": True,
						"node": record.to_dict(),
						"node_token": token,
					})
					return

				# POST /unregister
				if path == "/unregister":
					body = self._read_json()
					node_id = str(body.get("node_id") or "")
					if not node_id:
						self._write_json(400, {"ok": False, "error": "node_id is required"})
						return
					if not self._check_node_auth(node_id):
						self._write_json(403, {"ok": False, "error": "invalid node token"})
						return
					server.token_manager.revoke(node_id)
					ok = server.registry.unregister(node_id)
					self._write_json(200, {"ok": ok})
					return

				# POST /heartbeat
				if path == "/heartbeat":
					body = self._read_json()
					node_id = str(body.get("node_id") or "")
					if not self._check_node_auth(node_id):
						self._write_json(403, {"ok": False, "error": "invalid node token"})
						return
					ok = server.registry.heartbeat(node_id)
					self._write_json(200, {"ok": ok})
					return

				# POST /message
				if path == "/message":
					body = self._read_json()
					valid, reason = validate_message(body)
					if not valid:
						self._write_json(400, {"ok": False, "error": reason})
						return
					mode = str(body.get("mode") or "direct")
					if mode == "broadcast":
						result = server.router.broadcast(body)
					elif mode == "type":
						node_type = str(body.get("node_type") or "")
						result = server.router.route_to_type(node_type=node_type, message=body)
					elif mode == "capability":
						cap = str(body.get("capability") or "")
						if not cap:
							self._write_json(400, {"ok": False, "error": "capability is required for mode=capability"})
							return
						result = server.router.route_to_capability(capability=cap, message=body)
					else:
						result = server.router.route(body)
					self._write_json(200, result)
					return

				self._write_json(404, {"ok": False, "error": "not found"})

		return Handler

	def serve_forever(self) -> None:
		self.health_scanner.start()
		httpd = ThreadingHTTPServer(
			(self.config.host, self.config.port), self.create_handler()
		)
		addr = f"http://{self.config.host}:{self.config.port}"
		logger.info("listening at %s", addr)
		print(f"[physclaw-node-server] listening at {addr}")
		print(f"  heartbeat_timeout={self.config.heartbeat_timeout_sec}s"
			  f"  offline_timeout={self.config.offline_timeout_sec}s"
			  f"  scan_interval={self.config.health_scan_interval_sec}s")
		try:
			httpd.serve_forever()
		finally:
			self.health_scanner.stop()


def main() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
		datefmt="%H:%M:%S",
	)
	server = PhysClawNodeServer()
	server.serve_forever()


if __name__ == "__main__":
	main()
