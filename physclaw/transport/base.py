"""Channel abstract base class.

Every channel plugin (CLI/File/Discord/WhatsApp) must implement this interface.

Reference: OpenClaw s04_multi_channel.py Channel ABC
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from nanobot.transport.events import InboundMessage


class Channel(ABC):
    """Abstract base class for channel plugins."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique channel identifier, e.g. 'cli', 'file', 'discord'."""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable channel name for display."""
        ...

    @property
    @abstractmethod
    def max_text_length(self) -> int:
        """Maximum characters per message.

        Different channels have different limits:
        - Discord: 2000
        - WhatsApp: 4096
        - Telegram: 4096
        - CLI: unlimited (but long text affects readability)
        """
        ...

    @abstractmethod
    def receive(self) -> InboundMessage | None:
        """Non-blocking poll: return InboundMessage if available, else None."""
        ...

    @abstractmethod
    def send(self, text: str, media: list | None = None) -> None:
        """Send message to channel. Long text is automatically chunked."""
        ...

    def chunk_text(self, text: str) -> list[str]:
        """Split long text by channel limit.

        Strategy:
        1. Prefer splitting at paragraph boundaries (\\n\\n)
        2. Then at newlines (\\n)
        3. Then at spaces
        4. Hard cut as last resort
        """
        max_len = self.max_text_length
        if len(text) <= max_len:
            return [text]

        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break
            cut = remaining[:max_len]
            split_pos = cut.rfind("\n\n")
            if split_pos < max_len // 4:
                split_pos = cut.rfind("\n")
            if split_pos < max_len // 4:
                split_pos = cut.rfind(" ")
            if split_pos < max_len // 4:
                split_pos = max_len
            chunks.append(remaining[:split_pos].rstrip())
            remaining = remaining[split_pos:].lstrip()

        return [c for c in chunks if c]
