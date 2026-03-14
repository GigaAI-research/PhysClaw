"""All tool definitions, handlers, and dispatch.

Contains 20 tools organized from s02 (4 base) + s03 (16 extended):
  Base (s02):  bash, read_file, write_file, edit_file
  Files (s03): list_directory, head, tail, ls_detailed, du, diff_files
  Search:      search_in_files, find_files
  Git:         git_status, git_diff, git_log
  Network:     curl, wget
  Archive:     tar_create, tar_extract
  Utility:     get_current_time
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanobot.base.helpers import (
    WORKSPACE_DIR, ALLOWED_ROOT, MAX_TOOL_OUTPUT,
    safe_path, truncate, decode_output,
)


# ============================================================================
# Tool handler functions
# ============================================================================

# -- Base tools (s02) --

def tool_bash(command: str, timeout: int = 30) -> str:
    """Execute a shell command."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=False,
            timeout=timeout, cwd=str(ALLOWED_ROOT),
        )
        output = decode_output(result.stdout)
        if result.stderr:
            output += "\n--- stderr ---\n" + decode_output(result.stderr)
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_read_file(file_path: str) -> str:
    """Read file contents."""
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        if not target.is_file():
            return f"Error: Not a file: {file_path}"
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = target.read_text(encoding="gbk")
            except UnicodeDecodeError:
                return f"Error: Binary file, cannot read as text: {file_path}"
        return truncate(content)
    except Exception as exc:
        return f"Error: {exc}"


def tool_write_file(file_path: str, content: str) -> str:
    """Write content to a file."""
    try:
        target = safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {file_path}"
    except Exception as exc:
        return f"Error: {exc}"


def tool_edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Replace exact string in a file."""
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        content = target.read_text(encoding="utf-8")
        if old_string not in content:
            return f"Error: old_string not found in {file_path}"
        count = content.count(old_string)
        if count > 1:
            return f"Error: old_string found {count} times; must be unique"
        new_content = content.replace(old_string, new_string, 1)
        target.write_text(new_content, encoding="utf-8")
        return f"Successfully edited {file_path}"
    except Exception as exc:
        return f"Error: {exc}"


# -- Filesystem tools (s03) --

def tool_list_directory(path: str = ".") -> str:
    target = safe_path(path)
    if not target.is_dir():
        return f"Error: not a directory: {path}"
    entries = []
    for entry in sorted(target.iterdir()):
        if entry.name.startswith("."):
            continue
        kind = "dir" if entry.is_dir() else "file"
        size = entry.stat().st_size if entry.is_file() else 0
        entries.append(f"  [{kind}] {entry.name}" + (f"  ({size} bytes)" if size else ""))
    return "\n".join(entries) if entries else "(empty directory)"


def tool_head(file_path: str, lines: int = 10) -> str:
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        content = target.read_text(encoding="utf-8")
        all_lines = content.splitlines()
        result = "\n".join(all_lines[:lines])
        if len(all_lines) > lines:
            result += f"\n... [{len(all_lines) - lines} more lines]"
        return result
    except Exception as exc:
        return f"Error: {exc}"


def tool_tail(file_path: str, lines: int = 10) -> str:
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        content = target.read_text(encoding="utf-8")
        all_lines = content.splitlines()
        result_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        result = "\n".join(result_lines)
        if len(all_lines) > lines:
            result = f"... [{len(all_lines) - lines} lines skipped]\n" + result
        return result
    except Exception as exc:
        return f"Error: {exc}"


def tool_ls_detailed(path: str = ".") -> str:
    try:
        target = safe_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        import platform
        cmd = f"dir {target}" if platform.system() == "Windows" else f"ls -lah {target}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, timeout=10, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[empty]"
        return truncate(output)
    except Exception as exc:
        return f"Error: {exc}"


def tool_du(path: str = ".") -> str:
    try:
        target = safe_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        result = subprocess.run(f"du -h {target}", shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no output]"
        return truncate(output)
    except Exception as exc:
        return f"Error: {exc}"


def tool_diff_files(file1: str, file2: str) -> str:
    try:
        t1, t2 = safe_path(file1), safe_path(file2)
        if not t1.exists():
            return f"Error: File not found: {file1}"
        if not t2.exists():
            return f"Error: File not found: {file2}"
        result = subprocess.run(f"diff -u {t1} {t2}", shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        if result.returncode == 0:
            return "[files are identical]"
        return truncate(decode_output(result.stdout))
    except Exception as exc:
        return f"Error: {exc}"


# -- Search tools --

def tool_search_in_files(pattern: str, path: str = ".", file_pattern: str | None = None) -> str:
    try:
        target = safe_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        check_rg = subprocess.run("rg --version", shell=True, capture_output=True, text=False, timeout=5)
        if check_rg.returncode == 0:
            cmd_parts = ["rg", "--color=never", "--line-number"]
            if file_pattern:
                cmd_parts.extend(["--glob", file_pattern])
            cmd_parts.extend([pattern, str(target)])
        else:
            cmd_parts = ["grep", "-rn", pattern, str(target)]
            if file_pattern:
                cmd_parts.extend(["--include", file_pattern])
        result = subprocess.run(" ".join(cmd_parts), shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no matches found]"
        return truncate(output)
    except subprocess.TimeoutExpired:
        return "Error: Search timed out after 30s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_find_files(pattern: str, path: str = ".") -> str:
    try:
        target = safe_path(path)
        if not target.exists():
            return f"Error: Path not found: {path}"
        check_fd = subprocess.run("fd --version", shell=True, capture_output=True, text=False, timeout=5)
        cmd = f"fd --color=never {pattern} {target}" if check_fd.returncode == 0 else f"find {target} -name {pattern}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no files found]"
        return truncate(output)
    except Exception as exc:
        return f"Error: {exc}"


# -- Git tools --

def tool_git_status() -> str:
    try:
        result = subprocess.run("git status", shell=True, capture_output=True, text=False, timeout=10, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout)
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except Exception as exc:
        return f"Error: {exc}"


def tool_git_diff(file_path: str | None = None, staged: bool = False) -> str:
    try:
        cmd = "git diff"
        if staged:
            cmd += " --staged"
        if file_path:
            safe_path(file_path)
            cmd += f" -- {file_path}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no changes]"
        return truncate(output)
    except Exception as exc:
        return f"Error: {exc}"


def tool_git_log(max_count: int = 10, file_path: str | None = None) -> str:
    try:
        cmd = f"git log --oneline -n {max_count}"
        if file_path:
            safe_path(file_path)
            cmd += f" -- {file_path}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=False, timeout=30, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no commits]"
        return truncate(output)
    except Exception as exc:
        return f"Error: {exc}"


# -- Network tools --

def tool_curl(url: str, method: str = "GET", headers: dict | None = None, data: str | None = None, timeout: int = 30) -> str:
    try:
        cmd_parts = ["curl", "-s", "-X", method]
        if headers:
            for k, v in headers.items():
                cmd_parts.extend(["-H", f"{k}: {v}"])
        if data:
            cmd_parts.extend(["-d", data])
        cmd_parts.append(url)
        result = subprocess.run(" ".join(cmd_parts), shell=True, capture_output=True, text=False, timeout=timeout, cwd=str(ALLOWED_ROOT))
        output = decode_output(result.stdout) or "[no output]"
        return truncate(output)
    except subprocess.TimeoutExpired:
        return f"Error: curl timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_wget(url: str, output_path: str | None = None, timeout: int = 60) -> str:
    try:
        cmd_parts = ["wget", "-q"]
        if output_path:
            target = safe_path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            cmd_parts.extend(["-O", str(target)])
        cmd_parts.append(url)
        result = subprocess.run(" ".join(cmd_parts), shell=True, capture_output=True, text=False, timeout=timeout, cwd=str(ALLOWED_ROOT))
        if result.returncode == 0:
            return f"Successfully downloaded" + (f" to {output_path}" if output_path else "")
        return decode_output(result.stderr) or "Error: wget failed"
    except Exception as exc:
        return f"Error: {exc}"


# -- Archive tools --

def tool_tar_create(archive_path: str, source_paths: list[str]) -> str:
    try:
        target = safe_path(archive_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        verified = [str(safe_path(src)) for src in source_paths if safe_path(src).exists()]
        if not verified:
            return "Error: No valid source paths"
        result = subprocess.run(f"tar -czf {target} {' '.join(verified)}", shell=True, capture_output=True, text=False, timeout=60, cwd=str(ALLOWED_ROOT))
        return f"Successfully created archive: {archive_path}" if result.returncode == 0 else "Error: tar create failed"
    except Exception as exc:
        return f"Error: {exc}"


def tool_tar_extract(archive_path: str, dest_path: str = ".") -> str:
    try:
        archive = safe_path(archive_path)
        if not archive.exists():
            return f"Error: Archive not found: {archive_path}"
        dest = safe_path(dest_path)
        dest.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(f"tar -xzf {archive} -C {dest}", shell=True, capture_output=True, text=False, timeout=60, cwd=str(ALLOWED_ROOT))
        return f"Successfully extracted to: {dest_path}" if result.returncode == 0 else "Error: tar extract failed"
    except Exception as exc:
        return f"Error: {exc}"


# -- Utility --

def tool_get_current_time() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# Tool schemas (Anthropic format -> OpenAI format conversion)
# ============================================================================

_BASE_TOOLS = [
    {"name": "bash", "description": "Execute a shell command.", "input_schema": {"type": "object", "properties": {"command": {"type": "string", "description": "The command to execute."}, "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)."}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string", "description": "Path to the file."}}, "required": ["file_path"]}},
    {"name": "write_file", "description": "Write content to a file.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string", "description": "Path to the file."}, "content": {"type": "string", "description": "Content to write."}}, "required": ["file_path", "content"]}},
    {"name": "edit_file", "description": "Replace an exact string in a file.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string", "description": "Path to the file."}, "old_string": {"type": "string", "description": "Exact string to find."}, "new_string": {"type": "string", "description": "Replacement string."}}, "required": ["file_path", "old_string", "new_string"]}},
]

_EXTENDED_TOOLS = [
    {"name": "list_directory", "description": "List files and directories at the given path.", "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path (default: '.')."}}}},
    {"name": "get_current_time", "description": "Get the current date and time in ISO format.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_in_files", "description": "Search for text pattern in files using ripgrep or grep.", "input_schema": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Regex pattern to search for."}, "path": {"type": "string", "description": "Directory to search in (default: '.')."}, "file_pattern": {"type": "string", "description": "File pattern filter (e.g., '*.py')."}}, "required": ["pattern"]}},
    {"name": "find_files", "description": "Find files by name pattern.", "input_schema": {"type": "object", "properties": {"pattern": {"type": "string", "description": "File name pattern (e.g., '*.py')."}, "path": {"type": "string", "description": "Directory to search in (default: '.')."}}, "required": ["pattern"]}},
    {"name": "head", "description": "Display the first N lines of a file.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "lines": {"type": "integer", "description": "Number of lines (default: 10)."}}, "required": ["file_path"]}},
    {"name": "tail", "description": "Display the last N lines of a file.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "lines": {"type": "integer", "description": "Number of lines (default: 10)."}}, "required": ["file_path"]}},
    {"name": "git_status", "description": "Get git repository status.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "git_diff", "description": "Show git changes.", "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}, "staged": {"type": "boolean", "description": "Show staged changes (default: false)."}}}},
    {"name": "git_log", "description": "Show git commit history.", "input_schema": {"type": "object", "properties": {"max_count": {"type": "integer", "description": "Max commits (default: 10)."}, "file_path": {"type": "string"}}}},
    {"name": "diff_files", "description": "Compare two files.", "input_schema": {"type": "object", "properties": {"file1": {"type": "string"}, "file2": {"type": "string"}}, "required": ["file1", "file2"]}},
    {"name": "ls_detailed", "description": "List directory with detailed info.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "du", "description": "Show disk usage.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "curl", "description": "Make HTTP requests.", "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string"}, "headers": {"type": "object"}, "data": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["url"]}},
    {"name": "wget", "description": "Download a file from a URL.", "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "output_path": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["url"]}},
    {"name": "tar_create", "description": "Create a tar.gz archive.", "input_schema": {"type": "object", "properties": {"archive_path": {"type": "string"}, "source_paths": {"type": "array", "items": {"type": "string"}}}, "required": ["archive_path", "source_paths"]}},
    {"name": "tar_extract", "description": "Extract a tar.gz archive.", "input_schema": {"type": "object", "properties": {"archive_path": {"type": "string"}, "dest_path": {"type": "string"}}, "required": ["archive_path"]}},
]

# Combined tool schemas
TOOLS = _BASE_TOOLS + _EXTENDED_TOOLS


def tools_to_openai_format(tool_list: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool schemas to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_list
    ]


TOOLS_OPENAI = tools_to_openai_format(TOOLS)

# Handler dispatch table
TOOL_HANDLERS: dict[str, Any] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "list_directory": tool_list_directory,
    "get_current_time": tool_get_current_time,
    "search_in_files": tool_search_in_files,
    "find_files": tool_find_files,
    "head": tool_head,
    "tail": tool_tail,
    "git_status": tool_git_status,
    "git_diff": tool_git_diff,
    "git_log": tool_git_log,
    "diff_files": tool_diff_files,
    "ls_detailed": tool_ls_detailed,
    "du": tool_du,
    "curl": tool_curl,
    "wget": tool_wget,
    "tar_create": tool_tar_create,
    "tar_extract": tool_tar_extract,
}


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the corresponding handler."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return handler(**tool_input)
    except TypeError as exc:
        return f"Error: Invalid arguments for {tool_name}: {exc}"
    except Exception as exc:
        return f"Error: {tool_name} failed: {exc}"
