"""Workflow state and final result types.

:class:`WorkflowState` is JSON-serialisable so a run can be checkpointed after
each phase and resumed later (see ``orchestrator/persistence.py``).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from schemas import PlannerOutput, ReviewerOutput, RouterOutput

STATE_VERSION = 1


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class IterationRecord:
    index: int
    executor_report: str
    git_diff: str
    validation_output: str
    review: Optional[ReviewerOutput] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "executor_report": self.executor_report,
            "git_diff": self.git_diff,
            "validation_output": self.validation_output,
            "review": self.review.model_dump() if self.review else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IterationRecord":
        review = data.get("review")
        return cls(
            index=data["index"],
            executor_report=data.get("executor_report", ""),
            git_diff=data.get("git_diff", ""),
            validation_output=data.get("validation_output", ""),
            review=ReviewerOutput.model_validate(review) if review else None,
        )


@dataclass
class WorkflowState:
    """Mutable state threaded through a single orchestration run."""

    task: str
    repository: str
    workflow: str = "code_generation"
    router_output: Optional[RouterOutput] = None
    planner_output: Optional[PlannerOutput] = None
    repository_context: str = ""
    modified_files: list[str] = field(default_factory=list)
    git_diff: str = ""
    validation_output: str = ""
    reviewer_feedback: Optional[ReviewerOutput] = None
    iteration: int = 0
    history: list[IterationRecord] = field(default_factory=list)
    pull_request: str = ""
    run_id: str = field(default_factory=_new_run_id)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_version": STATE_VERSION,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": time.time(),
            "task": self.task,
            "repository": self.repository,
            "workflow": self.workflow,
            "router_output": self.router_output.model_dump() if self.router_output else None,
            "planner_output": self.planner_output.model_dump() if self.planner_output else None,
            "modified_files": self.modified_files,
            "git_diff": self.git_diff,
            "validation_output": self.validation_output,
            "reviewer_feedback": self.reviewer_feedback.model_dump() if self.reviewer_feedback else None,
            "iteration": self.iteration,
            "pull_request": self.pull_request,
            "history": [record.to_dict() for record in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        router = data.get("router_output")
        plan = data.get("planner_output")
        feedback = data.get("reviewer_feedback")
        return cls(
            task=data["task"],
            repository=data["repository"],
            workflow=data.get("workflow", "code_generation"),
            router_output=RouterOutput.model_validate(router) if router else None,
            planner_output=PlannerOutput.model_validate(plan) if plan else None,
            modified_files=list(data.get("modified_files", [])),
            git_diff=data.get("git_diff", ""),
            validation_output=data.get("validation_output", ""),
            reviewer_feedback=ReviewerOutput.model_validate(feedback) if feedback else None,
            iteration=data.get("iteration", 0),
            history=[IterationRecord.from_dict(r) for r in data.get("history", [])],
            pull_request=data.get("pull_request", ""),
            run_id=data.get("run_id", _new_run_id()),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class OrchestratorResult:
    """Clean, caller-facing result. Callers need not know about iterations."""

    status: str  # PASS | FIX | ERROR
    task: str
    workflow: str
    iterations: int
    summary: str
    modified_files: list[str] = field(default_factory=list)
    plan: Optional[PlannerOutput] = None
    review: Optional[ReviewerOutput] = None
    git_diff: str = ""
    pull_request: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task": self.task,
            "workflow": self.workflow,
            "iterations": self.iterations,
            "summary": self.summary,
            "modified_files": self.modified_files,
            "pull_request": self.pull_request,
            "plan": self.plan.model_dump() if self.plan else None,
            "review": self.review.model_dump() if self.review else None,
            "error": self.error,
        }
