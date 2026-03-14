from __future__ import annotations

import os
from dataclasses import dataclass

from shared.config import load_node_server_config


def _env_int(name: str, default: int) -> int:
	raw = os.getenv(name)
	if raw is None:
		return default
	try:
		return int(raw)
	except ValueError:
		return default


@dataclass(frozen=True)
class ServerRuntimeConfig:
	host: str
	port: int
	# 健康检测
	heartbeat_timeout_sec: int = 30       # 无心跳 → unhealthy
	offline_timeout_sec: int = 300        # 无心跳 → 自动注销
	health_scan_interval_sec: int = 10    # 扫描间隔
	# 消息投递
	delivery_timeout_sec: int = 10        # HTTP 投递超时
	delivery_max_retries: int = 3         # 最大重试次数


def get_server_runtime_config() -> ServerRuntimeConfig:
	cfg = load_node_server_config()
	return ServerRuntimeConfig(
		host=cfg.host,
		port=cfg.port,
		heartbeat_timeout_sec=_env_int("PHYSCLAW_HEARTBEAT_TIMEOUT", 30),
		offline_timeout_sec=_env_int("PHYSCLAW_OFFLINE_TIMEOUT", 300),
		health_scan_interval_sec=_env_int("PHYSCLAW_HEALTH_SCAN_INTERVAL", 10),
		delivery_timeout_sec=_env_int("PHYSCLAW_DELIVERY_TIMEOUT", 10),
		delivery_max_retries=_env_int("PHYSCLAW_DELIVERY_MAX_RETRIES", 3),
	)

