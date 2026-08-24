"""Reviewer agent: judges the implementation and returns PASS/FIX."""

from __future__ import annotations

from events import EventSink, null_sink
from models import OpenRouterClient
from schemas import PlannerOutput, ReviewerOutput
from tools import ToolRegistry

from .base import Agent, parse_json_object
from .prompt_loader import compose, load_prompt


class ReviewerAgent:
    def __init__(
        self,
        client: OpenRouterClient,
        model: str,
        tools: ToolRegistry,
        *,
        temperature: float | None = 0.0,
        max_tool_iterations: int = 30,
        emit: EventSink = null_sink,
        extra: str = "",
    ) -> None:
        self._agent = Agent(
            name="reviewer",
            model=model,
            system_prompt=compose(load_prompt("reviewer"), extra),
            client=client,
            tools=tools,
            temperature=temperature,
            max_tool_iterations=max_tool_iterations,
            emit=emit,
        )

    def review(
        self,
        task: str,
        plan: PlannerOutput,
        executor_report: str,
        git_diff: str,
        validation_output: str,
    ) -> ReviewerOutput:
        prompt = "\n\n".join(
            [
                f"ORIGINAL USER REQUEST:\n{task}",
                f"IMPLEMENTATION PLAN:\n{plan.as_context()}",
                f"EXECUTOR REPORT:\n{executor_report}",
                f"GIT DIFF:\n{git_diff or '(no diff available)'}",
                f"VALIDATION OUTPUT:\n{validation_output or '(none captured)'}",
                "Review the work and return the JSON verdict.",
            ]
        )
        result = self._agent.run(prompt)
        data = parse_json_object(result.text)
        return ReviewerOutput.model_validate(data)
