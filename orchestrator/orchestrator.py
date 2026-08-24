"""The orchestration engine.

Wires the router, planner, executor and reviewer into a workflow:

    task -> Router -> Planner -> [Executor -> Validation -> Reviewer]* -> result

All routing and model-selection decisions live here; agents stay generic.

The public surface is a single method::

    result = Orchestrator().run(task="Implement OAuth login", repository=".")

The caller does not need to know which models ran or how many iterations occurred.

Two optional capabilities:

* **Live narrative** — pass an ``emit`` sink (e.g. ``ConsoleSink``) to stream the
  agents' thoughts and tool calls to stderr as the run progresses.
* **Checkpoint / resume** — pass ``checkpoint`` to persist state after every phase,
  and ``resume=True`` to continue an interrupted run from where it stopped.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Optional

from agents import ExecutorAgent, PlannerAgent, ReviewerAgent, RouterAgent
from events import INFO, PHASE, VERDICT, Event, EventSink, null_sink
from models import OpenRouterClient
from schemas import RouterOutput
from tools import Workspace, build_tools

from .config import DEFAULT_WORKFLOW, WORKFLOWS, OrchestratorConfig
from .persistence import load_state, save_state
from .state import IterationRecord, OrchestratorResult, WorkflowState

logger = logging.getLogger("orch.orchestrator")


class Orchestrator:
    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        client: Optional[OpenRouterClient] = None,
        emit: EventSink = null_sink,
    ) -> None:
        self.config = config or OrchestratorConfig.from_env()
        self.client = client or OpenRouterClient()
        self.emit = emit

    def run(
        self,
        task: Optional[str] = None,
        repository: str = ".",
        workflow: Optional[str] = None,
        *,
        checkpoint: Optional[str] = None,
        resume: bool = False,
    ) -> OrchestratorResult:
        """Run (or resume) the full workflow.

        ``workflow`` may be forced by the caller; otherwise the Router chooses.
        ``checkpoint`` is a JSON path; when set, state is saved after each phase.
        ``resume=True`` loads that checkpoint (if present) and continues.
        """
        checkpoint_path = Path(checkpoint) if checkpoint else None

        # -- Load or initialise state -------------------------------------
        if checkpoint_path and resume and checkpoint_path.exists():
            state = load_state(checkpoint_path)
            self.emit(Event(
                INFO, "orchestrator",
                f"Resuming run {state.run_id} (workflow={state.workflow}, "
                f"completed_iterations={len(state.history)})",
            ))
        else:
            if not task:
                raise ValueError("A task is required to start a new run.")
            workspace0 = Workspace(repository)
            state = WorkflowState(task=task, repository=str(workspace0.root), workflow=workflow or DEFAULT_WORKFLOW)

        workspace = Workspace(state.repository)
        read_tools = build_tools(workspace, writable=False)
        write_tools = build_tools(workspace, writable=True)

        def checkpoint_save() -> None:
            if checkpoint_path:
                save_state(checkpoint_path, state)

        try:
            # 1) Route --------------------------------------------------------
            if state.router_output is None:
                self.emit(Event(PHASE, "router", "classifying task"))
                router_output = self._route(state.task, workflow, read_tools)
                state.router_output = router_output
                state.workflow = router_output.workflow
                checkpoint_save()
            else:
                router_output = state.router_output
            models = self._resolve_models(router_output)
            self.emit(Event(
                PHASE, "orchestrator",
                f"workflow={state.workflow}  planner={models.planner}  "
                f"executor={models.executor}  reviewer={models.reviewer}",
            ))

            # 2) Plan ---------------------------------------------------------
            if state.planner_output is None:
                self.emit(Event(PHASE, "planner", "producing implementation plan"))
                planner = PlannerAgent(self.client, models.planner, read_tools,
                                       max_tool_iterations=self.config.max_tool_iterations, emit=self.emit)
                state.planner_output = planner.plan(state.task, state.workflow)
                checkpoint_save()
            plan = state.planner_output
            self.emit(Event(PHASE, "planner", f"plan ready: complexity={plan.complexity}, {len(plan.steps)} step(s)"))

            # Already finished on a previous run?
            if state.history and state.history[-1].review and state.history[-1].review.passed:
                self.emit(Event(VERDICT, "reviewer", "PASS (from checkpoint)"))
                return self._result("PASS", state, state.history[-1].executor_report)

            # 3) Execute / Review loop ---------------------------------------
            executor = ExecutorAgent(self.client, models.executor, write_tools,
                                     max_tool_iterations=self.config.max_tool_iterations, emit=self.emit)
            reviewer = ReviewerAgent(self.client, models.reviewer, read_tools,
                                     max_tool_iterations=self.config.max_tool_iterations, emit=self.emit)

            completed = len(state.history)
            last = state.history[-1] if state.history else None
            feedback: Optional[str] = last.review.as_feedback() if last and last.review else None

            for iteration in range(completed + 1, self.config.max_iterations + 1):
                state.iteration = iteration
                self.emit(Event(PHASE, "executor", f"iteration {iteration}/{self.config.max_iterations}"))

                report = executor.execute(state.task, plan, reviewer_feedback=feedback)
                git_diff = self._git_diff(write_tools)
                self.emit(Event(PHASE, "orchestrator", "running validation commands"))
                validation = self._run_validation(plan, write_tools)
                state.git_diff = git_diff
                state.validation_output = validation
                state.modified_files = self._modified_files(write_tools, report.modified_files)

                self.emit(Event(PHASE, "reviewer", "reviewing changes"))
                review = reviewer.review(state.task, plan, report.report, git_diff, validation)
                state.reviewer_feedback = review
                state.history.append(
                    IterationRecord(
                        index=iteration,
                        executor_report=report.report,
                        git_diff=git_diff,
                        validation_output=validation,
                        review=review,
                    )
                )
                checkpoint_save()

                if review.passed:
                    self.emit(Event(VERDICT, "reviewer", f"PASS on iteration {iteration}"))
                    return self._result("PASS", state, report.report)

                self.emit(Event(VERDICT, "reviewer", f"FIX — {len(review.issues)} issue(s); looping"))
                feedback = review.as_feedback()

            last_report = state.history[-1].executor_report if state.history else ""
            return self._result("FIX", state, last_report)

        except Exception as exc:  # noqa: BLE001 - surface as a clean result
            logger.exception("orchestration failed")
            self.emit(Event(INFO, "orchestrator", f"ERROR: {exc}"))
            checkpoint_save()
            return OrchestratorResult(
                status="ERROR",
                task=state.task,
                workflow=state.workflow,
                iterations=state.iteration,
                summary=f"Orchestration failed: {exc}",
                plan=state.planner_output,
                review=state.reviewer_feedback,
                error=str(exc),
            )

    # -- internals ---------------------------------------------------------

    def _route(self, task: str, forced: Optional[str], read_tools) -> RouterOutput:
        if forced:
            workflow = forced if forced in WORKFLOWS else DEFAULT_WORKFLOW
            return RouterOutput(workflow=workflow, reason="forced by caller")
        if not self.config.use_router:
            return RouterOutput(workflow=DEFAULT_WORKFLOW, reason="router disabled")
        router = RouterAgent(self.client, self.config.models.router, read_tools, emit=self.emit)
        try:
            return router.classify(task)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            logger.warning("router failed (%s); using default workflow", exc)
            self.emit(Event(INFO, "router", f"failed ({exc}); using default workflow"))
            return RouterOutput(workflow=DEFAULT_WORKFLOW, reason="router error fallback")

    def _resolve_models(self, router_output: RouterOutput):
        models = self.config.resolve_models(router_output.workflow)
        # A router may further override individual roles.
        return replace(
            models,
            planner=router_output.planner or models.planner,
            executor=router_output.executor or models.executor,
            reviewer=router_output.reviewer or models.reviewer,
        )

    @staticmethod
    def _git_diff(tools) -> str:
        try:
            return tools.execute("git_diff", {})
        except Exception:  # noqa: BLE001
            return ""

    def _run_validation(self, plan, tools) -> str:
        """Independently re-run the plan's validation commands for the record.

        The executor also runs these, but capturing them here gives the reviewer
        a trustworthy, orchestrator-observed signal.
        """
        if not plan.validation:
            return "(no validation commands specified)"
        blocks = []
        for command in plan.validation[:10]:
            try:
                output = tools.execute("run_command", {"command": command})
            except Exception as exc:  # noqa: BLE001
                output = f"[failed to run] {exc}"
            blocks.append(f"$ {command}\n{output}")
        return "\n\n".join(blocks)

    @staticmethod
    def _modified_files(tools, executor_touched: list[str]) -> list[str]:
        # Prefer git for accuracy (catches side effects the executor didn't report).
        try:
            status = tools.execute("git_status", {})
        except Exception:  # noqa: BLE001
            status = ""
        files: list[str] = []
        if status and not status.startswith("[") and status != "(clean)":
            for line in status.splitlines():
                line = line.strip()
                if not line or line.startswith("##"):
                    continue
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    path = parts[1].split("-> ")[-1].strip()
                    files.append(path)
        if files:
            return sorted(set(files))
        # Non-git repo: fall back to the paths the executor actually wrote.
        return sorted(set(executor_touched))

    @staticmethod
    def _result(status: str, state: WorkflowState, executor_report: str) -> OrchestratorResult:
        summary = _summarise(executor_report)
        return OrchestratorResult(
            status=status,
            task=state.task,
            workflow=state.workflow,
            iterations=state.iteration,
            summary=summary,
            modified_files=state.modified_files,
            plan=state.planner_output,
            review=state.reviewer_feedback,
            git_diff=state.git_diff,
        )


def _summarise(report: str, limit: int = 1200) -> str:
    report = (report or "").strip()
    if len(report) <= limit:
        return report
    return report[:limit].rstrip() + " [...]"
