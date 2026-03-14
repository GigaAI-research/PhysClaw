from __future__ import annotations

from typing import Any, Dict, Tuple
from uuid import uuid4

REQUIRED_MESSAGE_FIELDS = ("action", "source", "target", "payload")


def validate_message(data: Dict[str, Any]) -> Tuple[bool, str]:
	if not isinstance(data, dict):
		return False, "message must be a JSON object"
	for field in REQUIRED_MESSAGE_FIELDS:
		if field not in data:
			return False, f"missing field: {field}"
	if not isinstance(data.get("payload"), dict):
		return False, "payload must be object"
	# 自动补充 message_id（如未提供）
	if "message_id" not in data:
		data["message_id"] = str(uuid4())
	return True, "ok"
