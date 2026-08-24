"""Git inspection tools (read-only): status and diff."""

from __future__ import annotations

import subprocess

from .registry import Tool
from .workspace import Workspace

MAX_OUTPUT_CHARS = 30_000


def _git(ws: Workspace, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "[git not installed]"
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "not a git repository" in err.lower():
            return "[not a git repository]"
        return f"[git error] {err}"
    out = proc.stdout
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + "\n[... diff truncated ...]"
    return out.strip() or "(clean)"


def git_status(ws: Workspace) -> str:
    return _git(ws, ["status", "--short", "--branch"])


def git_diff(ws: Workspace) -> str:
    # Include staged and unstaged changes.
    return _git(ws, ["diff", "HEAD"])


def git_tools(ws: Workspace) -> list[Tool]:
    return [
        Tool(
            name="git_status",
            description="Show the git working-tree status (short form).",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: git_status(ws),
        ),
        Tool(
            name="git_diff",
            description="Show the git diff of working-tree changes against HEAD.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: git_diff(ws),
        ),
    ]
