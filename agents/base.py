"""Base agent: a tool-calling loop over a single model.

Every agent — router, planner, executor, reviewer — is an instance of this class.
The only differences are the model, the system prompt, and which tools it can use.
The orchestrator owns all routing decisions; agents just run their loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from events import THOUGHT, TOOL, TOOL_RESULT, Event, EventSink, null_sink
from models import OpenRouterClient
from tools import ToolError, ToolRegistry

logger = logging.getLogger("orch.agent")


@dataclass
class AgentResult:
    text: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_log: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)


# Tools that change the filesystem, and the argument holding the affected path.
_MODIFYING_TOOLS = {
    "write_file": "path",
    "edit_file": "path",
    "delete_file": "path",
    "rename_file": "destination",
}


class Agent:
    def __init__(
        self,
        name: str,
        model: str,
        system_prompt: str,
        client: OpenRouterClient,
        tools: ToolRegistry,
        *,
        temperature: Optional[float] = None,
        max_tool_iterations: int = 40,
        emit: EventSink = null_sink,
    ) -> None:
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.client = client
        self.tools = tools
        self.temperature = temperature
        self.max_tool_iterations = max_tool_iterations
        self.emit = emit
        self.log = logging.getLogger(f"orch.agent.{name}")

    def run(self, user_content: str) -> AgentResult:
        """Run the tool-calling loop until the model returns a final message."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]
        tool_specs = self.tools.specs() or None
        tool_log: list[str] = []
        modified: list[str] = []

        for step in range(1, self.max_tool_iterations + 1):
            result = self.client.chat(
                model=self.model,
                messages=messages,
                tools=tool_specs,
                temperature=self.temperature,
            )
            # Append the assistant turn verbatim so tool_call_ids line up.
            messages.append(self._assistant_dict(result.message))

            # Surface the model's interim natural-language output as a "thought".
            if result.content and result.content.strip():
                self.emit(Event(THOUGHT, self.name, result.content))

            tool_calls = result.tool_calls
            if not tool_calls:
                self.log.info("finished after %d step(s)", step)
                return AgentResult(text=result.content, messages=messages,
                                   tool_log=tool_log, modified_files=_dedupe(modified))

            for call in tool_calls:
                fn = call.get("function", {}) or {}
                self.emit(Event(TOOL, self.name, f"{fn.get('name', '?')}({_short_raw(fn.get('arguments'))})"))
                tool_msg, summary = self._dispatch(call)
                self.emit(Event(TOOL_RESULT, self.name, tool_msg.get("content", "")))
                messages.append(tool_msg)
                tool_log.append(summary)
                _track_modified(fn, tool_msg.get("content", ""), modified)

        self.log.warning("hit max_tool_iterations (%d)", self.max_tool_iterations)
        # Force a final answer with no tools available.
        messages.append(
            {
                "role": "user",
                "content": "Tool budget exhausted. Provide your final answer now without calling tools.",
            }
        )
        result = self.client.chat(model=self.model, messages=messages, temperature=self.temperature)
        return AgentResult(text=result.content, messages=messages,
                           tool_log=tool_log, modified_files=_dedupe(modified))

    def _dispatch(self, call: dict[str, Any]) -> tuple[dict[str, Any], str]:
        call_id = call.get("id", "")
        fn = call.get("function", {}) or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments", "") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError as exc:
            content = f"[tool-error] Could not parse arguments as JSON: {exc}"
            self.log.warning("%s: %s", name, content)
            return self._tool_dict(call_id, name, content), f"{name} -> arg parse error"

        try:
            content = self.tools.execute(name, args)
            summary = f"{name}({_short(args)}) -> ok"
        except ToolError as exc:
            content = f"[tool-error] {exc}"
            summary = f"{name} -> error"
        self.log.info("%s", summary)
        return self._tool_dict(call_id, name, content), summary

    @staticmethod
    def _assistant_dict(message: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            out["tool_calls"] = message["tool_calls"]
        return out

    @staticmethod
    def _tool_dict(call_id: str, name: str, content: str) -> dict[str, Any]:
        return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}


def _short(args: dict[str, Any], limit: int = 80) -> str:
    text = json.dumps(args, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen)


def _track_modified(fn: dict[str, Any], result_content: str, modified: list[str]) -> None:
    """Record the path a filesystem-modifying tool call touched (on success)."""
    name = fn.get("name", "")
    key = _MODIFYING_TOOLS.get(name)
    if not key or result_content.startswith("[tool-error]"):
        return
    raw = fn.get("arguments", "") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except json.JSONDecodeError:
        return
    path = args.get(key)
    if isinstance(path, str) and path:
        modified.append(path)


def _short_raw(raw: Any, limit: int = 120) -> str:
    """Compact preview of raw tool-call arguments (a JSON string or dict)."""
    if isinstance(raw, str):
        text = raw
    else:
        try:
            text = json.dumps(raw, ensure_ascii=False)
        except TypeError:
            text = str(raw)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def parse_json_object(text: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON object from a model's text output.

    Handles bare JSON, ```json fenced blocks, and surrounding prose.
    """
    if not text or not text.strip():
        raise ValueError("Empty response; expected a JSON object.")

    cleaned = text.strip()

    # Strip code fences if present.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)
        # ['', 'json\n{...}\n', ' trailing'] -> take the middle
        cleaned = cleaned[1] if len(cleaned) > 1 else text
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
        cleaned = cleaned.strip("`").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to the first balanced {...} span.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])

    raise ValueError(f"Could not parse a JSON object from response:\n{text[:500]}")
