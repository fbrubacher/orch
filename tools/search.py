"""Code search tool. Uses ripgrep when available, else a pure-Python fallback."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

from .registry import Tool
from .workspace import Workspace

MAX_MATCHES = 200
_IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"}


def _search_ripgrep(ws: Workspace, pattern: str, glob: str | None) -> str:
    cmd = ["rg", "--line-number", "--no-heading", "--color=never", "--max-count", "50"]
    if glob:
        cmd += ["--glob", glob]
    cmd += ["--", pattern, "."]
    proc = subprocess.run(cmd, cwd=str(ws.root), capture_output=True, text=True, timeout=60)
    if proc.returncode not in (0, 1):  # 1 == no matches
        raise RuntimeError(proc.stderr.strip() or "ripgrep failed")
    lines = proc.stdout.splitlines()[:MAX_MATCHES]
    return "\n".join(lines) if lines else "(no matches)"


def _search_python(ws: Workspace, pattern: str, glob: str | None) -> str:
    regex = re.compile(pattern)
    matches: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ws.root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
        for name in filenames:
            if glob and not _glob_match(name, glob):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ws.root)
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if regex.search(line):
                            matches.append(f"{rel}:{lineno}:{line.rstrip()[:300]}")
                            if len(matches) >= MAX_MATCHES:
                                return "\n".join(matches)
            except OSError:
                continue
    return "\n".join(matches) if matches else "(no matches)"


def _glob_match(name: str, glob: str) -> bool:
    import fnmatch

    # allow patterns like '*.py' or 'src/**/*.ts' (match on basename part)
    return fnmatch.fnmatch(name, glob.split("/")[-1])


def _search_code(ws: Workspace, pattern: str, glob: str | None = None) -> str:
    if shutil.which("rg"):
        try:
            return _search_ripgrep(ws, pattern, glob)
        except Exception:  # noqa: BLE001 - fall back to python
            pass
    return _search_python(ws, pattern, glob)


def search_tools(ws: Workspace) -> list[Tool]:
    return [
        Tool(
            name="search_code",
            description="Search the repository for a regular-expression pattern and return matching file:line results.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression to search for."},
                    "glob": {"type": "string", "description": "Optional file glob filter, e.g. '*.py'."},
                },
                "required": ["pattern"],
            },
            handler=lambda pattern, glob=None: _search_code(ws, pattern, glob),
        )
    ]
