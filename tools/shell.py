"""Shell command tool.

The executor uses this to run tests, builds and linters. Commands run with the
workspace root as the working directory and a bounded timeout.
"""

from __future__ import annotations

import subprocess

from .registry import Tool
from .workspace import Workspace

MAX_OUTPUT_CHARS = 30_000


def _run_command(ws: Workspace, command: str, timeout: int = 600) -> str:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"[timeout] Command exceeded {timeout}s and was killed: {command}"

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = stdout
    if stderr:
        combined += ("\n" if combined else "") + "[stderr]\n" + stderr
    if len(combined) > MAX_OUTPUT_CHARS:
        combined = combined[:MAX_OUTPUT_CHARS] + "\n[... output truncated ...]"
    return f"exit_code={proc.returncode}\n{combined}".strip()


def shell_tools(ws: Workspace) -> list[Tool]:
    return [
        Tool(
            name="run_command",
            description=(
                "Run a shell command in the repository root and return its exit code and output. "
                "Use for tests, builds, linters and type checks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute."},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 600)."},
                },
                "required": ["command"],
            },
            handler=lambda command, timeout=600: _run_command(ws, command, timeout),
        )
    ]
