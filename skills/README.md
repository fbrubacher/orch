# Skills

A **skill** is a reusable, named block of guidance injected into an agent's
system prompt at runtime. Each skill is one Markdown file, `skills/<name>.md`.

- Skills named in a workflow (or in config / `--skills`) are appended to the
  **executor's** prompt — except finalizer skills (see below), which run *after*
  review passes.
- The special skill **`open-pr`** is a *finalizer*: its guidance drives a dedicated
  step that runs only once the reviewer returns PASS (so a PR is opened only for
  verified work). It is automatically skipped when the target isn't a git repo, has
  no `origin` remote, or `gh` isn't installed.

## Built-in skills

| Skill            | Applies to | Effect                                                        |
|------------------|------------|---------------------------------------------------------------|
| `atomic-commits` | executor   | Work on an `orch/…` branch; commit each logical change small.  |
| `open-pr`        | finalizer  | After PASS: push the branch and open a PR with `gh` (no merge).|

## Add your own

Drop a `skills/my-policy.md` file, then reference it:

```bash
orch --task "..." --skills my-policy
# or set ORCH_SKILLS=my-policy in .orch_env, or add it to a workflow in config.py
```

Default skills per workflow live in `orchestrator/config.py` (`DEFAULT_SKILLS` and
each `WorkflowSpec.skills`). A global `default_prompt` (env `ORCH_DEFAULT_PROMPT`)
is injected into *every* agent.
