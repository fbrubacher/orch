"""Configuration: default models, workflow routing table, and tunables.

Nothing here is model-specific behaviour — only defaults. Every value can be
overridden via environment variables or by constructing the config directly,
keeping the orchestrator model-agnostic.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Optional

# Default OpenRouter model ids for each role.
DEFAULT_ROUTER = "openai/gpt-5.6"
DEFAULT_PLANNER = "openai/gpt-5.6"
DEFAULT_EXECUTOR = "deepseek/deepseek-v4-pro"
DEFAULT_REVIEWER = "openai/gpt-5.6"

# A stronger executor used for design-heavy workflows (architecture/security).
# The concrete model is chosen at runtime from OrchestratorConfig.strong_model
# (env: ORCH_MODEL_STRONG), so the escalation target is never hard-coded.
DEFAULT_STRONG_MODEL = "openai/gpt-5.6"

# Skills (reusable prompt policies in skills/<name>.md) applied by default to
# code-changing workflows. Override per-workflow via WorkflowSpec.skills, globally
# via ORCH_SKILLS, or per-run via --skills.
DEFAULT_SKILLS = ["atomic-commits", "open-pr"]

# Skills that run as a post-review *finalizer* rather than being injected into the
# executor prompt. `open-pr` opens a PR only after the reviewer returns PASS.
FINALIZER_SKILLS = {"open-pr"}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)


@dataclass(frozen=True)
class ModelConfig:
    router: str = DEFAULT_ROUTER
    planner: str = DEFAULT_PLANNER
    executor: str = DEFAULT_EXECUTOR
    reviewer: str = DEFAULT_REVIEWER

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            router=os.getenv("ORCH_MODEL_ROUTER", DEFAULT_ROUTER),
            planner=os.getenv("ORCH_MODEL_PLANNER", DEFAULT_PLANNER),
            executor=os.getenv("ORCH_MODEL_EXECUTOR", DEFAULT_EXECUTOR),
            reviewer=os.getenv("ORCH_MODEL_REVIEWER", DEFAULT_REVIEWER),
        )


@dataclass(frozen=True)
class WorkflowSpec:
    """Per-workflow model overrides.

    An explicit ``planner``/``executor``/``reviewer`` id pins that role; ``None``
    means 'use the base model'. ``strong_executor=True`` escalates the executor to
    the configured strong model at resolution time.
    """

    name: str
    planner: Optional[str] = None
    executor: Optional[str] = None
    reviewer: Optional[str] = None
    strong_executor: bool = False
    # Skills for this workflow. None -> inherit DEFAULT_SKILLS; [] -> no skills.
    skills: Optional[list[str]] = None


# Routing table. Design/security work escalates the executor to the strong model;
# everything else inherits the defaults. New workflows plug in here without
# touching orchestration logic.
WORKFLOWS: dict[str, WorkflowSpec] = {
    "code_generation": WorkflowSpec("code_generation"),
    "bug_fix": WorkflowSpec("bug_fix"),
    "documentation": WorkflowSpec("documentation"),
    "test_generation": WorkflowSpec("test_generation"),
    "refactor": WorkflowSpec("refactor"),
    # Architecture is a design activity — no commits/PR policy by default.
    "architecture": WorkflowSpec("architecture", strong_executor=True, skills=[]),
    "security": WorkflowSpec("security", strong_executor=True),
}

DEFAULT_WORKFLOW = "code_generation"


@dataclass
class OrchestratorConfig:
    models: ModelConfig = field(default_factory=ModelConfig)
    # Executor model for workflows flagged strong_executor (architecture/security).
    strong_model: str = DEFAULT_STRONG_MODEL
    max_iterations: int = 3
    use_router: bool = True
    temperature: Optional[float] = None
    max_tool_iterations: int = 40
    # Guidance injected into agents. ``default_prompt`` goes to every agent;
    # ``skills`` are extra skill names appended to whatever the workflow selects.
    default_prompt: str = ""
    skills: list[str] = field(default_factory=list)
    # Tri-state open-PR control: None -> follow the workflow's skills (auto),
    # True -> force on, False -> force off.
    open_pr: Optional[bool] = None

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        open_pr_env = os.getenv("ORCH_OPEN_PR")
        open_pr: Optional[bool] = None
        if open_pr_env is not None:
            open_pr = open_pr_env not in {"0", "false", "False", ""}
        return cls(
            models=ModelConfig.from_env(),
            strong_model=os.getenv("ORCH_MODEL_STRONG", DEFAULT_STRONG_MODEL),
            max_iterations=int(os.getenv("ORCH_MAX_ITERATIONS", "3")),
            use_router=os.getenv("ORCH_USE_ROUTER", "1") not in {"0", "false", "False"},
            default_prompt=os.getenv("ORCH_DEFAULT_PROMPT", ""),
            skills=_split_csv(os.getenv("ORCH_SKILLS", "")),
            open_pr=open_pr,
        )

    def resolve_models(self, workflow: str) -> ModelConfig:
        """Apply a workflow's overrides on top of the base models."""
        spec = WORKFLOWS.get(workflow)
        if spec is None:
            return self.models
        executor = spec.executor or (self.strong_model if spec.strong_executor else self.models.executor)
        return replace(
            self.models,
            planner=spec.planner or self.models.planner,
            executor=executor,
            reviewer=spec.reviewer or self.models.reviewer,
        )

    def resolve_skills(self, workflow: str) -> list[str]:
        """Effective skill list: workflow skills (or DEFAULT_SKILLS) + config skills."""
        spec = WORKFLOWS.get(workflow)
        base = DEFAULT_SKILLS if (spec is None or spec.skills is None) else spec.skills
        return _dedupe([*base, *self.skills])
