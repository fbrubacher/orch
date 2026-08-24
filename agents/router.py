"""Router agent: classifies the task and picks a workflow."""

from __future__ import annotations

from events import EventSink, null_sink
from models import OpenRouterClient
from schemas import RouterOutput
from tools import ToolRegistry

from .base import Agent, parse_json_object
from .prompt_loader import load_prompt


class RouterAgent:
    def __init__(
        self,
        client: OpenRouterClient,
        model: str,
        tools: ToolRegistry,
        *,
        temperature: float | None = 0.0,
        max_tool_iterations: int = 10,
        emit: EventSink = null_sink,
    ) -> None:
        self._agent = Agent(
            name="router",
            model=model,
            system_prompt=load_prompt("router"),
            client=client,
            tools=tools,
            temperature=temperature,
            max_tool_iterations=max_tool_iterations,
            emit=emit,
        )

    def classify(self, task: str) -> RouterOutput:
        result = self._agent.run(f"Classify this software-engineering task:\n\n{task}")
        data = parse_json_object(result.text)
        return RouterOutput.model_validate(data)
