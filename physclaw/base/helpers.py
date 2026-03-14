"""Core utility functions and constants.

Provides workspace path management, path safety validation, and output helpers.
Reference: OpenClaw s02_tool_use.py base infrastructure.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Workspace directory: all file operations are sandboxed here
WORKSPACE_DIR = Path(os.getenv("WORKSPACE_DIR", str(Path.home() / "workspace")))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Security boundary: all file access must stay within this root
ALLOWED_ROOT = WORKSPACE_DIR.resolve()

# Maximum tool output length to prevent context overflow
MAX_TOOL_OUTPUT = int(os.getenv("MAX_TOOL_OUTPUT", "16000"))


def safe_path(relative_path: str) -> Path:
    """Resolve a relative path and ensure it stays within ALLOWED_ROOT.

    Raises:
        ValueError: If the resolved path escapes the allowed root.
    """
    target = (WORKSPACE_DIR / relative_path).resolve()
    if not str(target).startswith(str(ALLOWED_ROOT)):
        raise ValueError(f"Path escapes workspace: {relative_path}")
    return target


def truncate(text: str, max_len: int = MAX_TOOL_OUTPUT) -> str:
    """Truncate text to max_len, adding a notice if truncated."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n\n[... truncated {len(text) - max_len} chars ...]\n\n" + text[-half:]


def decode_output(raw: bytes) -> str:
    """Decode subprocess output, trying utf-8 then gbk then latin-1."""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


# ANSI color helpers
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
