"""Offline unit tests — no OpenRouter calls required.

Run with:  python -m pytest -q   (or: python tests/test_offline.py)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import parse_json_object
from events import THOUGHT, ConsoleSink, Event
from orchestrator.config import OrchestratorConfig, WORKFLOWS
from orchestrator.persistence import load_state, save_state
from orchestrator.state import IterationRecord, WorkflowState
from schemas import PlannerOutput, ReviewerOutput, RouterOutput
from tools import Workspace, build_tools
from tools.registry import ToolError


# ---- JSON parsing -----------------------------------------------------------

def test_parse_plain_json():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    text = "Here you go:\n```json\n{\"status\": \"PASS\"}\n```\n"
    assert parse_json_object(text) == {"status": "PASS"}


def test_parse_json_with_prose():
    assert parse_json_object("blah {\"x\": true} trailing")["x"] is True


# ---- Schemas ----------------------------------------------------------------

def test_planner_accepts_executor_alias():
    plan = PlannerOutput.model_validate({"summary": "s", "complexity": "COMPLEX", "executor": "gpt"})
    assert plan.preferred_executor == "gpt"
    assert plan.complexity == "complex"


def test_planner_normalises_bad_complexity():
    plan = PlannerOutput.model_validate({"complexity": "nonsense"})
    assert plan.complexity == "medium"


def test_reviewer_defaults_to_fix():
    review = ReviewerOutput.model_validate({"status": "weird"})
    assert review.status == "FIX"
    assert not review.passed


def test_router_normalises_workflow():
    assert RouterOutput.model_validate({"workflow": "Bug-Fix"}).workflow == "bug_fix"
    assert RouterOutput.model_validate({"workflow": "???"}).workflow == "code_generation"


# ---- Config routing ---------------------------------------------------------

def test_architecture_routes_executor_to_strong_model():
    config = OrchestratorConfig()
    models = config.resolve_models("architecture")
    assert models.executor == config.strong_model
    # planner/reviewer keep defaults
    assert models.planner == config.models.planner


def test_strong_model_is_configurable():
    config = OrchestratorConfig(strong_model="anthropic/claude-opus-4.1")
    assert config.resolve_models("security").executor == "anthropic/claude-opus-4.1"
    # non-strong workflows are unaffected
    assert config.resolve_models("bug_fix").executor == config.models.executor


# ---- Tools ------------------------------------------------------------------

def test_filesystem_roundtrip(tmp_path):
    ws = Workspace(tmp_path)
    tools = build_tools(ws, writable=True)
    tools.execute("write_file", {"path": "a/b.txt", "content": "hello"})
    assert tools.execute("read_file", {"path": "a/b.txt"}) == "hello"
    tools.execute("edit_file", {"path": "a/b.txt", "old_string": "hello", "new_string": "world"})
    assert tools.execute("read_file", {"path": "a/b.txt"}) == "world"
    listing = tools.execute("list_files", {"path": ".", "pattern": "*.txt"})
    assert "a/b.txt" in listing
    tools.execute("delete_file", {"path": "a/b.txt"})


def test_read_only_registry_has_no_write_tools(tmp_path):
    ws = Workspace(tmp_path)
    tools = build_tools(ws, writable=False)
    assert "write_file" not in tools
    assert "run_command" not in tools
    assert "read_file" in tools


def test_workspace_blocks_escape(tmp_path):
    ws = Workspace(tmp_path)
    tools = build_tools(ws, writable=True)
    try:
        tools.execute("read_file", {"path": "../../etc/passwd"})
    except ToolError:
        return
    raise AssertionError("expected ToolError for path escape")


def test_run_command_captures_exit_code(tmp_path):
    ws = Workspace(tmp_path)
    tools = build_tools(ws, writable=True)
    out = tools.execute("run_command", {"command": "echo hi"})
    assert "exit_code=0" in out
    assert "hi" in out


# ---- Persistence / resume ---------------------------------------------------

def test_state_roundtrip(tmp_path):
    state = WorkflowState(task="do a thing", repository=str(tmp_path), workflow="bug_fix")
    state.router_output = RouterOutput(workflow="bug_fix", reason="test")
    state.planner_output = PlannerOutput.model_validate(
        {"summary": "s", "complexity": "simple", "steps": ["a", "b"], "validation": ["pytest -q"]}
    )
    review = ReviewerOutput.model_validate({"status": "FIX", "issues": [{"severity": "high", "description": "boom"}]})
    state.history.append(IterationRecord(1, "did stuff", "diff", "output", review))
    state.iteration = 1

    path = tmp_path / "run.json"
    save_state(path, state)
    loaded = load_state(path)

    assert loaded.task == "do a thing"
    assert loaded.workflow == "bug_fix"
    assert loaded.planner_output.steps == ["a", "b"]
    assert loaded.run_id == state.run_id
    assert len(loaded.history) == 1
    assert loaded.history[0].review.status == "FIX"


def test_atomic_save_leaves_no_tmp(tmp_path):
    state = WorkflowState(task="t", repository=str(tmp_path))
    path = tmp_path / "run.json"
    save_state(path, state)
    assert path.exists()
    assert not (tmp_path / "run.json.tmp").exists()


# ---- Event sink -------------------------------------------------------------

def test_console_sink_writes(tmp_path):
    import io

    buf = io.StringIO()
    sink = ConsoleSink(buf, color=False)
    sink(Event(THOUGHT, "planner", "I will read the config first"))
    out = buf.getvalue()
    assert "planner" in out
    assert "read the config" in out


# ---- Manual runner ----------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    import traceback
    from pathlib import Path

    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            passed += 1
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
