"""Standardized inbound message format.

All channels convert their messages to InboundMessage before entering the agent.

Reference: OpenClaw s04_multi_channel.py InboundMessage
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """Standardized inbound message.

    All channel messages are converted to this format before entering the agent.
    """

    channel: str           # Source channel ID (e.g. "cli", "file", "discord")
    sender: str            # Sender identifier (e.g. username, user ID)
    text: str              # Message text content
    media_urls: list[str] = field(default_factory=list)   # Attachment URL list
    thread_id: str | None = None                          # Thread/topic ID
    timestamp: float = field(default_factory=time.time)   # Unix timestamp
