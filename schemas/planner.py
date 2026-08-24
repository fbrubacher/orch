"""Structured output produced by the Planner agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

Complexity = str  # "simple" | "medium" | "complex"


class PlannerOutput(BaseModel):
    summary: str = ""
    objective: str = ""
    complexity: Complexity = "medium"
    files: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    preferred_executor: str = "auto"

    @model_validator(mode="before")
    @classmethod
    def _accept_aliases(cls, data: Any) -> Any:
        """Tolerate the ``executor`` key some prompt variants emit."""
        if isinstance(data, dict) and "preferred_executor" not in data and "executor" in data:
            data = {**data, "preferred_executor": data["executor"]}
        return data

    @field_validator("complexity")
    @classmethod
    def _normalise_complexity(cls, value: str) -> str:
        value = (value or "medium").strip().lower()
        return value if value in {"simple", "medium", "complex"} else "medium"

    def as_context(self) -> str:
        """Render the plan as readable text to feed downstream agents."""
        lines = [
            f"SUMMARY: {self.summary}",
            f"OBJECTIVE: {self.objective}",
            f"COMPLEXITY: {self.complexity}",
        ]
        if self.files:
            lines.append("FILES:\n" + "\n".join(f"  - {f}" for f in self.files))
        if self.steps:
            lines.append("STEPS:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self.steps)))
        if self.constraints:
            lines.append("CONSTRAINTS:\n" + "\n".join(f"  - {c}" for c in self.constraints))
        if self.validation:
            lines.append("VALIDATION COMMANDS:\n" + "\n".join(f"  - {v}" for v in self.validation))
        if self.risks:
            lines.append("RISKS:\n" + "\n".join(f"  - {r}" for r in self.risks))
        if self.success_criteria:
            lines.append("SUCCESS CRITERIA:\n" + "\n".join(f"  - {s}" for s in self.success_criteria))
        return "\n".join(lines)
