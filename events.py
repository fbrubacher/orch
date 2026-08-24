"""Lightweight event stream for surfacing agent activity to a human.

Agents and the orchestrator emit :class:`Event` objects through a sink callable.
The default :class:`ConsoleSink` prints a readable narrative to stderr — the
model's interim text ("thoughts"), each tool call, and phase transitions — while
stdout stays reserved for the final result (so ``--json`` remains parseable).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable, TextIO

# Event kinds.
PHASE = "phase"          # orchestrator-level milestone
THOUGHT = "thought"      # a model's interim natural-language output
TOOL = "tool"            # a tool call the model requested
TOOL_RESULT = "result"   # the (truncated) result of a tool call
VERDICT = "verdict"      # reviewer PASS/FIX
INFO = "info"            # miscellaneous notice


@dataclass
class Event:
    kind: str
    agent: str
    message: str


EventSink = Callable[[Event], None]


def null_sink(event: Event) -> None:  # noqa: D401 - no-op sink
    return None


_ANSI = {
    PHASE: "\033[1;36m",     # bold cyan
    THOUGHT: "\033[0;90m",   # grey
    TOOL: "\033[0;33m",      # yellow
    TOOL_RESULT: "\033[0;90m",
    VERDICT: "\033[1;32m",   # bold green
    INFO: "\033[0;34m",      # blue
}
_RESET = "\033[0m"

_MARKERS = {
    PHASE: "==>",
    THOUGHT: "  .",
    TOOL: "  >",
    TOOL_RESULT: "    ",
    VERDICT: "***",
    INFO: " i ",
}


class ConsoleSink:
    """Human-readable event printer."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        color: bool | None = None,
        max_thought_chars: int = 2000,
        max_result_chars: int = 400,
    ) -> None:
        self.stream = stream or sys.stderr
        self.color = self.stream.isatty() if color is None else color
        self.max_thought_chars = max_thought_chars
        self.max_result_chars = max_result_chars

    def __call__(self, event: Event) -> None:
        marker = _MARKERS.get(event.kind, "   ")
        message = event.message
        if event.kind == THOUGHT:
            message = _truncate(message, self.max_thought_chars)
        elif event.kind == TOOL_RESULT:
            message = _first_line(_truncate(message, self.max_result_chars))

        head = f"{marker} [{event.agent}]"
        text = f"{head} {message}" if message else head
        if self.color:
            color = _ANSI.get(event.kind, "")
            text = f"{color}{text}{_RESET}"
        print(text, file=self.stream, flush=True)


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


def _first_line(text: str) -> str:
    text = (text or "").strip()
    first, _, rest = text.partition("\n")
    return first + (" …" if rest.strip() else "")
