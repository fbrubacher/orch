"""Structured output produced by the Router agent."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator

KNOWN_WORKFLOWS = {
    "code_generation",
    "bug_fix",
    "documentation",
    "test_generation",
    "architecture",
    "security",
    "refactor",
}


class RouterOutput(BaseModel):
    workflow: str = "code_generation"
    # Optional per-role model overrides the router may suggest.
    planner: Optional[str] = None
    executor: Optional[str] = None
    reviewer: Optional[str] = None
    reason: str = ""

    @field_validator("workflow")
    @classmethod
    def _normalise_workflow(cls, value: str) -> str:
        value = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
        return value if value in KNOWN_WORKFLOWS else "code_generation"
