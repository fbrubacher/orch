"""Structured output produced by the Reviewer agent."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ReviewIssue(BaseModel):
    severity: str = "medium"  # low | medium | high
    file: str = ""
    description: str = ""
    recommendation: str = ""

    @field_validator("severity")
    @classmethod
    def _normalise_severity(cls, value: str) -> str:
        value = (value or "medium").strip().lower()
        return value if value in {"low", "medium", "high"} else "medium"


class ReviewerOutput(BaseModel):
    status: str = "FIX"  # PASS | FIX
    issues: list[ReviewIssue] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def _normalise_status(cls, value: str) -> str:
        value = (value or "").strip().upper()
        return value if value in {"PASS", "FIX"} else "FIX"

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_feedback(self) -> str:
        if not self.issues:
            return "Reviewer requested changes but listed no specific issues."
        blocks = []
        for i, issue in enumerate(self.issues, start=1):
            blocks.append(
                f"[{i}] ({issue.severity}) {issue.file}\n"
                f"    Problem: {issue.description}\n"
                f"    Fix: {issue.recommendation}"
            )
        return "REVIEWER FEEDBACK — address every issue:\n" + "\n".join(blocks)
