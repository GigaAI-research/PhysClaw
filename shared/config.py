from __future__ import annotations

import os
from dataclasses import dataclass




def _env_int(name: str, default: int) -> int:
	raw = os.getenv(name)
	if raw is None:
		return default
	try:
		return int(raw)
	except ValueError:
		return default


@dataclass(frozen=True)
class NodeServerConfig:
	host: str = "127.0.0.1"
	port: int = 8765

	@property
	def base_url(self) -> str:
		return f"http://{self.host}:{self.port}"


def load_node_server_config() -> NodeServerConfig:
	return NodeServerConfig(
		host=os.getenv("PHYSCLAW_NODE_SERVER_HOST", "127.0.0.1"),
		port=_env_int("PHYSCLAW_NODE_SERVER_PORT", 8765),
	)

