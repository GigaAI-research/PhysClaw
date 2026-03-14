"""NodeInfo: device description data structure.

Reference: OpenClaw src/infra/node-pairing.ts NodePairingPairedNode
Reference: OpenClaw src/infra/node-commands.ts
Reference: OpenClaw src/gateway/node-command-policy.ts
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeInfo:
    """Device description — reported by Node on registration.

    Fields:
        node_id:      unique device identifier (e.g. UUID)
        display_name: human-readable device name (e.g. "My iPhone")
        platform:     platform (ios / android / macos / linux / windows)
        version:      node client version
        caps:         capability list (e.g. ["camera", "location", "exec"])
        commands:     supported command list (e.g. ["system.run"])
        permissions:  permission map (e.g. {"camera": True})
    """

    node_id: str
    display_name: str = ""
    platform: str = ""
    version: str = ""
    caps: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    permissions: dict[str, bool] = field(default_factory=dict)

    def __repr__(self) -> str:
        name = self.display_name or self.node_id[:8]
        return f"NodeInfo({name}, platform={self.platform}, caps={self.caps})"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "version": self.version,
            "caps": self.caps,
            "commands": self.commands,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> NodeInfo:
        return cls(
            node_id=d.get("node_id", ""),
            display_name=d.get("display_name", ""),
            platform=d.get("platform", ""),
            version=d.get("version", ""),
            caps=d.get("caps", []),
            commands=d.get("commands", []),
            permissions=d.get("permissions", {}),
        )


# Node system command constants
# Reference: OpenClaw src/infra/node-commands.ts
NODE_CMD_SYSTEM_RUN = "system.run"
NODE_CMD_SYSTEM_NOTIFY = "system.notify"
NODE_CMD_SYSTEM_WHICH = "system.which"
NODE_CMD_CAMERA_SNAP = "camera.snap"
NODE_CMD_LOCATION = "location.get"
NODE_CMD_SCREEN_SNAP = "screen.snap"

# Default command allowlist
# Reference: OpenClaw src/gateway/node-command-policy.ts
DEFAULT_ALLOWED_COMMANDS = frozenset({
    NODE_CMD_SYSTEM_RUN,
    NODE_CMD_SYSTEM_NOTIFY,
    NODE_CMD_SYSTEM_WHICH,
    NODE_CMD_CAMERA_SNAP,
    NODE_CMD_LOCATION,
    NODE_CMD_SCREEN_SNAP,
})
