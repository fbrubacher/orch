"""Assemble tool registries for agents.

Read-only agents (planner, reviewer, router) get inspection tools only.
The executor additionally gets write and shell tools.
"""

from __future__ import annotations

from .filesystem import read_tools, write_tools
from .git import git_tools
from .registry import ToolRegistry
from .search import search_tools
from .shell import shell_tools
from .workspace import Workspace


def build_tools(workspace: Workspace, *, writable: bool) -> ToolRegistry:
    tools = [
        *read_tools(workspace),
        *search_tools(workspace),
        *git_tools(workspace),
    ]
    if writable:
        tools += write_tools(workspace)
        tools += shell_tools(workspace)
    return ToolRegistry(tools)
