"""Filesystem sandbox for tool execution.

All filesystem and shell tools resolve paths through a :class:`Workspace` so an
agent cannot read or write outside the target repository, and commands run with
the repository as the working directory.
"""

from __future__ import annotations

from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


class Workspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise WorkspaceError(f"Repository path does not exist: {self.root}")
        if not self.root.is_dir():
            raise WorkspaceError(f"Repository path is not a directory: {self.root}")

    def resolve(self, relative: str) -> Path:
        """Resolve a repo-relative path, refusing anything that escapes root."""
        candidate = (self.root / relative).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise WorkspaceError(
                f"Path {relative!r} escapes the workspace root {self.root}"
            )
        return candidate

    def relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path)
