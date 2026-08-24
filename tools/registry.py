"""Tool abstraction shared by every agent.

A :class:`Tool` couples a JSON-schema description (what the model sees) with a
Python handler (what actually runs). A :class:`ToolRegistry` groups tools and
knows how to render them in OpenAI/OpenRouter function-calling format and how to
dispatch a call coming back from the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

Handler = Callable[..., str]


class ToolError(RuntimeError):
    """Raised when a tool cannot be executed (bad args, missing file, ...)."""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the arguments object
    handler: Handler

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, arguments: dict[str, Any]) -> str:
        return self.handler(**arguments)


class ToolRegistry:
    """An ordered, name-addressable collection of tools."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.add(tool)

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        """OpenAI-format tool specs to send with a chat request."""
        return [tool.to_openai() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool: {name!r}")
        try:
            result = tool.run(arguments)
        except ToolError:
            raise
        except TypeError as exc:  # bad/missing arguments
            raise ToolError(f"Invalid arguments for {name!r}: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - surface as a tool error string
            raise ToolError(f"Tool {name!r} failed: {exc}") from exc
        return result if isinstance(result, str) else json.dumps(result)
