# Coding Orchestrator

A model-agnostic, multi-agent coding orchestrator that sits above
[OpenRouter](https://openrouter.ai) and coordinates several LLMs, each with a
single responsibility. It is not a chatbot — it's a workflow engine for software
engineering tasks (features, bug fixes, refactors, tests, docs, migrations,
performance, security, architecture).

```
task ──▶ Router ──▶ Planner ──▶ ┌─ Executor ─▶ Validation ─▶ Reviewer ─┐
                                └──────────── FIX (loop back) ──────────┘
                                                    │
                                                   PASS ──▶ result
```

## Agents

| Agent    | Default model            | Role                                             | Writes code? |
|----------|--------------------------|--------------------------------------------------|:------------:|
| Router   | `openai/gpt-5.6`         | Classify the task, choose a workflow + models    | no           |
| Planner  | `openai/gpt-5.6`         | Explore the repo, produce a structured plan      | no           |
| Executor | `deepseek/deepseek-v4-pro` | Edit files, run tests/build/lint, iterate      | **yes**      |
| Reviewer | `openai/gpt-5.6`         | Judge the result, return `PASS` / `FIX`          | no           |

Every agent is the *same* [`Agent`](agents/base.py) tool-calling loop. The only
differences are the **model**, the **system prompt** (in [`prompts/`](prompts)),
and which **tools** it may use (read-only for router/planner/reviewer; read +
write + shell for the executor). All routing decisions live in the
[`Orchestrator`](orchestrator/orchestrator.py) — no model-specific behaviour is
hard-coded into agents.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .orch_env.example .orch_env   # then set OPENROUTER_API_KEY (loaded automatically)
```

## Use

Public API — the caller states *what* and *where*; nothing else:

```python
from orchestrator import Orchestrator

result = Orchestrator().run(task="Implement OAuth login", repository=".")
print(result.status)          # PASS | FIX | ERROR
print(result.modified_files)
print(result.summary)
```

CLI:

```bash
.venv/bin/python main.py --task "Fix the failing date parser" --repo ../myproject
.venv/bin/python main.py --task "Add tests for utils" --workflow test_generation --json
.venv/bin/python main.py --task "..." --no-router --max-iterations 2 -v
```

### Live output

As it runs, the orchestrator streams a readable narrative to **stderr** — each
agent's interim "thoughts", every tool call and result, phase transitions, and the
reviewer's verdict — while **stdout** stays reserved for the final result (so
`--json` output remains parseable). Use `--quiet` to silence the stream.

```
==> [router] classifying task
==> [planner] producing implementation plan
  . [planner] I'll inspect the existing utils module first…
  > [planner] read_file({"path": "src/utils.py"})
==> [executor] iteration 1/3
  > [executor] write_file({"path": "src/text_utils.py", ...})
  > [executor] run_command({"command": "pytest -q"})
*** [reviewer] PASS on iteration 1
```

Programmatically, pass an `emit` sink to the `Orchestrator`:

```python
import sys
from orchestrator import Orchestrator
from events import ConsoleSink

Orchestrator(emit=ConsoleSink(sys.stderr)).run(task="...", repository=".")
```

Any `Callable[[events.Event], None]` works as a sink (e.g. append to a list, push
to a websocket, write JSONL) — `ConsoleSink` is just the default.

### Resume an interrupted run

With `--state PATH`, the orchestrator checkpoints its `WorkflowState` to JSON after
every phase (routing, planning, and each execute→review iteration). Add `--resume`
to continue from that checkpoint — it skips already-completed phases and picks up at
the next iteration:

```bash
# first run (may be interrupted at any point)
.venv/bin/python main.py --task "Migrate to SQLAlchemy 2.0" --repo . --state .orch-run.json

# continue where it left off (task/repo come from the checkpoint)
.venv/bin/python main.py --resume --state .orch-run.json
```

Checkpointing is between phases. If the process dies **mid-executor**, resuming
re-runs that iteration — the executor re-inspects the current (possibly partly
modified) repo and continues, so pointing at a git repo keeps this safe.

## Tools

Shared by every agent via [`build_tools`](tools/factory.py):

`read_file` · `write_file` · `edit_file` · `delete_file` · `rename_file` ·
`list_files` · `search_code` · `run_command` · `git_status` · `git_diff`

All paths are sandboxed to the target repository via [`Workspace`](tools/workspace.py);
shell commands run with the repo as the working directory.

## Configuration

### Config precedence (`.orch_env`)

The CLI loads `.orch_env` files **project-first**, so you can keep per-project
model choices next to each repo:

```
real exported env  >  <repo>/.orch_env  >  <orch install>/.orch_env  >  built-in defaults
```

The first source to define a key wins (loaded with `override=False`). So a
`.orch_env` in the repo you target with `--repo` overrides the install-level file;
put a shared `OPENROUTER_API_KEY` in the install file and per-project model choices
in each repo. Only the keys a file *sets* are overridden — unset keys fall through
to the next source. On startup the CLI prints which files it loaded:

```
config: loaded /path/to/repo/.orch_env, /path/to/orch/.orch_env
```

(Note: the **library** `Orchestrator` reads config from the process env / the
`OrchestratorConfig` you pass — the project-first `.orch_env` layering is a CLI
convenience in `main.py`.)

---

Everything is overridable via env vars (see [`.orch_env`](.orch_env)) or by
constructing [`OrchestratorConfig`](orchestrator/config.py) directly:

- `ORCH_MODEL_{ROUTER,PLANNER,EXECUTOR,REVIEWER}` — swap any model (any provider:
  `anthropic/...`, `openai/...`, `deepseek/...`, mixed freely).
- `ORCH_MODEL_STRONG` — executor used by design-heavy workflows.
- `ORCH_MAX_ITERATIONS` — executor/reviewer retry budget.
- `ORCH_USE_ROUTER=0` — skip routing, use the default workflow.

Workflows and their model overrides live in the [`WORKFLOWS`](orchestrator/config.py)
table. `architecture` and `security` set `strong_executor=True`, which resolves to
`OrchestratorConfig.strong_model` (env `ORCH_MODEL_STRONG`) at runtime — so the
escalation target is configurable, not hard-coded:

```python
from orchestrator import OrchestratorConfig
from orchestrator.config import ModelConfig

config = OrchestratorConfig(
    models=ModelConfig(executor="anthropic/claude-sonnet-4"),
    strong_model="anthropic/claude-opus-4.1",   # used for architecture/security
)
```

## Extending

- **New prompt** — edit the Markdown in `prompts/`; no code change.
- **New workflow** — add an entry to `WORKFLOWS`.
- **New model** — set an env var or pass a different `ModelConfig`.
- **New agent** (Test, Docs, Security, Performance, Database, Release, ...) —
  add a prompt + a thin wrapper around `Agent`, then invoke it from the
  orchestration loop.

## Project layout

```
orchestrator/   orchestrator.py · state.py · persistence.py · config.py · logging
agents/         base.py (tool loop) · router · planner · executor · reviewer
prompts/        router.md · planner.md · executor.md · reviewer.md
tools/          filesystem · git · shell · search · registry · workspace · factory
models/         openrouter.py (OpenAI-compatible client)
schemas/        planner · reviewer · router (Pydantic)
events.py       event stream + ConsoleSink (agent narrative)
tests/          test_offline.py (no network)
examples/       run_example.py
main.py         CLI entry point
```

## Tests

Offline tests need no API key or network:

```bash
.venv/bin/python tests/test_offline.py     # built-in runner
# or, if pytest is installed:
.venv/bin/pip install pytest && .venv/bin/python -m pytest -q
```
