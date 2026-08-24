"""Executor agent: carries out the plan by editing the repository."""

from __future__ import annotations

from dataclasses import dataclass

from events import EventSink, null_sink
from models import OpenRouterClient
from schemas import PlannerOutput
from tools import ToolRegistry

from .base import Agent
from .prompt_loader import compose, load_prompt


@dataclass
class ExecutionReport:
    report: str
    tool_log: list[str]
    modified_files: list[str]


class ExecutorAgent:
    def __init__(
        self,
        client: OpenRouterClient,
        model: str,
        tools: ToolRegistry,
        *,
        temperature: float | None = None,
        max_tool_iterations: int = 60,
        emit: EventSink = null_sink,
        extra: str = "",
    ) -> None:
        self._agent = Agent(
            name="executor",
            model=model,
            system_prompt=compose(load_prompt("executor"), extra),
            client=client,
            tools=tools,
            temperature=temperature,
            max_tool_iterations=max_tool_iterations,
            emit=emit,
        )

    def execute(
        self,
        task: str,
        plan: PlannerOutput,
        reviewer_feedback: str | None = None,
    ) -> ExecutionReport:
        sections = [
            f"ORIGINAL USER REQUEST:\n{task}",
            f"IMPLEMENTATION PLAN:\n{plan.as_context()}",
        ]
        if reviewer_feedback:
            sections.append(
                "This is a follow-up pass. A reviewer found issues with your previous "
                "work. Address them precisely and re-run validation.\n\n" + reviewer_feedback
            )
        else:
            sections.append("Execute the plan now. Run the listed validation commands before finishing.")
        result = self._agent.run("\n\n".join(sections))
        return ExecutionReport(
            report=result.text,
            tool_log=result.tool_log,
            modified_files=result.modified_files,
        )
