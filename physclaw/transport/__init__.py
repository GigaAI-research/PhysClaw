"""Multi-channel transport layer.

Provides InboundMessage, Channel ABC, CLIChannel, FileChannel, and ChannelRegistry.
"""

from nanobot.transport.events import InboundMessage
from nanobot.transport.base import Channel
from nanobot.transport.cli import CLIChannel
from nanobot.transport.file import FileChannel
from nanobot.transport.registry import ChannelRegistry

__all__ = ["InboundMessage", "Channel", "CLIChannel", "FileChannel", "ChannelRegistry"]
