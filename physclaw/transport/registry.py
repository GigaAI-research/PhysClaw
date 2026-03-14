"""Channel registry and gateway polling.

Reference: OpenClaw s04_multi_channel.py ChannelRegistry + gateway_poll_once
"""

from __future__ import annotations

from typing import Any

from nanobot.transport.events import InboundMessage
from nanobot.transport.base import Channel


class ChannelRegistry:
    """Channel registry: manages registration and lookup of channel plugins."""

    def __init__(self):
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register a channel."""
        if channel.id in self._channels:
            raise ValueError(f"Channel already registered: {channel.id}")
        self._channels[channel.id] = channel

    def get(self, channel_id: str) -> Channel | None:
        """Get channel by ID."""
        return self._channels.get(channel_id)

    def list_channels(self) -> list[Channel]:
        """Return all registered channels."""
        return list(self._channels.values())

    @property
    def channels(self) -> list[Channel]:
        """All registered channels (property access)."""
        return list(self._channels.values())

    def poll_all(self) -> list[InboundMessage]:
        """Poll all channels, collect new messages."""
        messages = []
        for channel in self._channels.values():
            msg = channel.receive()
            if msg is not None:
                messages.append(msg)
        return messages


def gateway_poll_once(
    registry: ChannelRegistry,
    session_store: Any,
) -> int:
    """Execute one full-channel poll, return number of messages processed.

    This is a single iteration of the gateway main loop:
    1. Poll all channels
    2. Process each message
    3. Return processed count
    """
    from nanobot.engine.loop import agent_loop

    messages = registry.poll_all()
    processed = 0

    for msg in messages:
        channel = registry.get(msg.channel)
        if not channel:
            print(f"  [gateway] Unknown channel: {msg.channel}, skipping")
            continue

        # Build session key: agent:channel:sender
        safe_sender = msg.sender.replace(":", "_").replace("/", "_")
        session_key = f"main:{msg.channel}:{safe_sender}"

        print(f"  [gateway] {msg.channel}:{msg.sender} -> session {session_key}")
        print(f"  [gateway] message: {msg.text[:80]}{'...' if len(msg.text) > 80 else ''}")

        try:
            response = agent_loop(msg.text, session_key, session_store)
            channel.send(response)
            processed += 1
            print(f"  [gateway] replied via {msg.channel}")
        except Exception as exc:
            error_msg = f"Error processing message: {exc}"
            print(f"  [gateway] {error_msg}")
            channel.send(f"[Error] {error_msg}")

    return processed
