"""Planner agent: produces a structured implementation plan."""

from __future__ import annotations

from events import EventSink, null_sink
from models import OpenRouterClient
from schemas import PlannerOutput
from tools import ToolRegistry

from .base import Agent, parse_json_object
from .prompt_loader import load_prompt


class PlannerAgent:
    def __init__(
        self,
        client: OpenRouterClient,
        model: str,
        tools: ToolRegistry,
        *,
        temperature: float | None = None,
        max_tool_iterations: int = 30,
        emit: EventSink = null_sink,
    ) -> None:
        self._agent = Agent(
            name="planner",
            model=model,
            system_prompt=load_prompt("planner"),
            client=client,
            tools=tools,
            temperature=temperature,
            max_tool_iterations=max_tool_iterations,
            emit=emit,
        )

    def plan(self, task: str, workflow: str) -> PlannerOutput:
        prompt = (
            f"Workflow: {workflow}\n\n"
            f"User request:\n{task}\n\n"
            "Explore the repository as needed, then return the plan JSON."
        )
        result = self._agent.run(prompt)
        data = parse_json_object(result.text)
        return PlannerOutput.model_validate(data)
