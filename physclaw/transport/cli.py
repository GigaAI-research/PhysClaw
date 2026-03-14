"""CLI channel: stdin/stdout interaction as a Channel plugin.

Reference: OpenClaw s04_multi_channel.py CLIChannel
"""

from __future__ import annotations

from nanobot.transport.events import InboundMessage
from nanobot.transport.base import Channel


class CLIChannel(Channel):
    """Command-line interactive channel."""

    def __init__(self):
        self._pending: InboundMessage | None = None

    @property
    def id(self) -> str:
        return "cli"

    @property
    def label(self) -> str:
        return "CLI (stdin/stdout)"

    @property
    def max_text_length(self) -> int:
        return 8000

    def enqueue(self, text: str, sender: str = "user") -> None:
        """Enqueue a message from outside (for gateway loop use)."""
        self._pending = InboundMessage(
            channel=self.id,
            sender=sender,
            text=text,
        )

    def receive(self) -> InboundMessage | None:
        """Return queued message, then clear. Non-blocking."""
        msg = self._pending
        self._pending = None
        return msg

    def send(self, text: str, media: list | None = None) -> None:
        """Output to stdout. Long text is automatically chunked."""
        chunks = self.chunk_text(text)
        for i, chunk in enumerate(chunks):
            if i > 0:
                print("---")
            print(chunk)
