"""File-based channel: monitors an inbox file for new content.

Reference: OpenClaw s04_multi_channel.py FileChannel
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from nanobot.transport.events import InboundMessage
from nanobot.transport.base import Channel
from nanobot.base.helpers import WORKSPACE_DIR

FILE_CHANNEL_INBOX = WORKSPACE_DIR / ".channels" / "file_inbox.txt"
FILE_CHANNEL_OUTBOX = WORKSPACE_DIR / ".channels" / "file_outbox.txt"


class FileChannel(Channel):
    """File-watching channel.

    Monitors inbox file for changes, treats new content as messages.
    Replies are written to outbox file.
    """

    def __init__(
        self,
        inbox_path: Path | None = None,
        outbox_path: Path | None = None,
    ):
        self._inbox = inbox_path or FILE_CHANNEL_INBOX
        self._outbox = outbox_path or FILE_CHANNEL_OUTBOX
        self._inbox.parent.mkdir(parents=True, exist_ok=True)
        if not self._inbox.exists():
            self._inbox.write_text("", encoding="utf-8")
        if not self._outbox.exists():
            self._outbox.write_text("", encoding="utf-8")
        # Track read position (byte offset) to avoid reprocessing
        self._read_offset: int = self._inbox.stat().st_size

    @property
    def id(self) -> str:
        return "file"

    @property
    def label(self) -> str:
        return f"File ({self._inbox.name})"

    @property
    def max_text_length(self) -> int:
        return 4000

    def receive(self) -> InboundMessage | None:
        """Check inbox file for new content. Non-blocking."""
        current_size = self._inbox.stat().st_size
        if current_size <= self._read_offset:
            return None

        new_content = None
        for encoding in ["utf-8", "utf-16-le", "gbk"]:
            try:
                with open(self._inbox, "r", encoding=encoding) as f:
                    f.seek(self._read_offset)
                    new_content = f.read()
                break
            except (UnicodeDecodeError, OSError):
                continue

        if new_content is None:
            return None

        self._read_offset = current_size
        lines = [line.strip() for line in new_content.strip().splitlines() if line.strip()]
        if not lines:
            return None

        text = lines[-1]
        return InboundMessage(
            channel=self.id,
            sender="file_user",
            text=text,
        )

    def send(self, text: str, media: list | None = None) -> None:
        """Append reply to outbox file."""
        chunks = self.chunk_text(text)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(self._outbox, "a", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(f"[{now}] {chunk}\n")
                f.write("---\n")
