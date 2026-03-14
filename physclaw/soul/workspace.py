"""Agent workspace and bootstrap file loading.

Each Agent has an independent workspace containing SOUL.md, MEMORY.md, and memory/ dir.

Reference: OpenClaw src/agents/workspace.ts loadWorkspaceBootstrapFiles()
Reference: OpenClaw src/agents/system-prompt.ts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from nanobot.routing.config import AgentConfig
from nanobot.base.helpers import WORKSPACE_DIR

log = logging.getLogger("soul")

# Default limits, matching OpenClaw
BOOTSTRAP_MAX_CHARS = 20_000       # Max chars per file
BOOTSTRAP_TOTAL_MAX_CHARS = 24_000  # Total chars across all files


@dataclass
class AgentWithSoulMemory(AgentConfig):
    """Extended AgentConfig with independent workspace.

    workspace_dir is the Agent's file root, containing SOUL.md / MEMORY.md / memory/.
    """

    workspace_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.workspace_dir is None:
            self.workspace_dir = WORKSPACE_DIR / self.id
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        (self.workspace_dir / "memory").mkdir(exist_ok=True)

    @property
    def soul_path(self) -> Path:
        return self.workspace_dir / "SOUL.md"

    @property
    def memory_md_path(self) -> Path:
        return self.workspace_dir / "MEMORY.md"

    @property
    def memory_dir(self) -> Path:
        return self.workspace_dir / "memory"


def _truncate_bootstrap(content: str, max_chars: int = BOOTSTRAP_MAX_CHARS) -> str:
    """Truncate bootstrap file: keep 70% head + 20% tail.

    Reference: OpenClaw src/agents/pi-embedded-helpers/bootstrap.ts
    """
    if len(content) <= max_chars:
        return content
    head_budget = int(max_chars * 0.70)
    tail_budget = int(max_chars * 0.20)
    head = content[:head_budget]
    tail = content[-tail_budget:] if tail_budget > 0 else ""
    return f"{head}\n\n[...truncated...]\n\n{tail}"


def load_workspace_bootstrap_files(workspace_dir: Path) -> list[dict[str, str]]:
    """Load workspace bootstrap files (SOUL.md and MEMORY.md).

    Returns [{name, content}] list in OpenClaw loading order.
    """
    files: list[dict[str, str]] = []
    total_chars = 0

    for name in ("SOUL.md", "MEMORY.md"):
        path = workspace_dir / name
        if not path.exists():
            continue
        if path.is_symlink():
            log.warning("Skipping symlink: %s", path)
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except Exception as e:
            log.warning("Failed to read %s: %s", path, e)
            continue
        if not raw:
            continue

        content = _truncate_bootstrap(raw)
        if total_chars + len(content) > BOOTSTRAP_TOTAL_MAX_CHARS:
            budget = max(0, BOOTSTRAP_TOTAL_MAX_CHARS - total_chars)
            if budget <= 0:
                break
            content = _truncate_bootstrap(raw, budget)

        files.append({"name": name, "content": content})
        total_chars += len(content)

    return files
