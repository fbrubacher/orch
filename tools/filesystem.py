"""Filesystem tools: read, write, edit, list."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .registry import Tool, ToolError
from .workspace import Workspace

MAX_READ_BYTES = 200_000
_IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"}


def _read_file(ws: Workspace, path: str) -> str:
    target = ws.resolve(path)
    if not target.exists():
        raise ToolError(f"File not found: {path}")
    if not target.is_file():
        raise ToolError(f"Not a file: {path}")
    data = target.read_bytes()
    truncated = len(data) > MAX_READ_BYTES
    text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n[... truncated at {MAX_READ_BYTES} bytes ...]"
    return text


def _write_file(ws: Workspace, path: str, content: str) -> str:
    target = ws.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    verb = "Overwrote" if existed else "Created"
    return f"{verb} {ws.relative(target)} ({len(content)} chars)."


def _edit_file(ws: Workspace, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    target = ws.resolve(path)
    if not target.exists():
        raise ToolError(f"File not found: {path}")
    original = target.read_text(encoding="utf-8")
    count = original.count(old_string)
    if count == 0:
        raise ToolError("old_string not found in file; no edit performed.")
    if count > 1 and not replace_all:
        raise ToolError(
            f"old_string is not unique ({count} matches). "
            "Provide more context or set replace_all=true."
        )
    updated = original.replace(old_string, new_string) if replace_all else original.replace(old_string, new_string, 1)
    target.write_text(updated, encoding="utf-8")
    return f"Edited {ws.relative(target)} ({count if replace_all else 1} replacement(s))."


def _delete_file(ws: Workspace, path: str) -> str:
    target = ws.resolve(path)
    if not target.exists():
        raise ToolError(f"Path not found: {path}")
    if target.is_dir():
        raise ToolError("Refusing to delete a directory. Delete files individually.")
    target.unlink()
    return f"Deleted {ws.relative(target)}."


def _rename_file(ws: Workspace, source: str, destination: str) -> str:
    src = ws.resolve(source)
    dst = ws.resolve(destination)
    if not src.exists():
        raise ToolError(f"Source not found: {source}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"Renamed {ws.relative(src)} -> {ws.relative(dst)}."


def _list_files(ws: Workspace, path: str = ".", pattern: str = "*", max_results: int = 400) -> str:
    base = ws.resolve(path)
    if not base.exists():
        raise ToolError(f"Path not found: {path}")
    if base.is_file():
        return ws.relative(base)
    results: list[str] = []
    for current in sorted(base.rglob("*")):
        if any(part in _IGNORED_DIRS for part in current.parts):
            continue
        if current.is_dir():
            continue
        if not fnmatch.fnmatch(current.name, pattern):
            continue
        results.append(ws.relative(current))
        if len(results) >= max_results:
            results.append(f"[... truncated at {max_results} results ...]")
            break
    return "\n".join(results) if results else "(no matching files)"


def read_tools(ws: Workspace) -> list[Tool]:
    return [
        Tool(
            name="read_file",
            description="Read the full contents of a file, relative to the repository root.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Repo-relative file path."}},
                "required": ["path"],
            },
            handler=lambda path: _read_file(ws, path),
        ),
        Tool(
            name="list_files",
            description="List files under a directory (recursive) optionally filtered by a glob pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to list. Defaults to repo root."},
                    "pattern": {"type": "string", "description": "Glob for file names, e.g. '*.py'. Defaults to '*'."},
                },
                "required": [],
            },
            handler=lambda path=".", pattern="*": _list_files(ws, path, pattern),
        ),
    ]


def write_tools(ws: Workspace) -> list[Tool]:
    return [
        Tool(
            name="write_file",
            description="Create or overwrite a file with the given content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            handler=lambda path, content: _write_file(ws, path, content),
        ),
        Tool(
            name="edit_file",
            description="Replace an exact substring in a file. Fails if old_string is missing or non-unique (unless replace_all).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "description": "Replace every occurrence. Defaults to false."},
                },
                "required": ["path", "old_string", "new_string"],
            },
            handler=lambda path, old_string, new_string, replace_all=False: _edit_file(
                ws, path, old_string, new_string, replace_all
            ),
        ),
        Tool(
            name="delete_file",
            description="Delete a single file.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            handler=lambda path: _delete_file(ws, path),
        ),
        Tool(
            name="rename_file",
            description="Rename or move a file within the repository.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
            handler=lambda source, destination: _rename_file(ws, source, destination),
        ),
    ]
