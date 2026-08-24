"""Command-line entry point for the coding orchestrator.

Usage:
    python main.py --task "Implement OAuth login" --repo .
    python main.py --task "Fix the failing date parser" --repo ../myproject --workflow bug_fix
    python main.py --task "..." --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from events import ConsoleSink, null_sink
from orchestrator import Orchestrator, OrchestratorConfig
from orchestrator.config import WORKFLOWS
from orchestrator.logging_setup import setup_logging

INSTALL_DIR = Path(__file__).resolve().parent


def load_env_files(repo: str | None) -> list[str]:
    """Load ``.orch_env`` config, project-first.

    Precedence, highest wins: real process env > project (``<repo>/.orch_env``)
    > install (``<orch>/.orch_env``). We load in that order with
    ``override=False``, so an already-set key is never clobbered — meaning the
    first file to define a key wins, and real exported env always wins.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # dotenv is optional
        return []
    loaded: list[str] = []
    candidates = []
    if repo:
        candidates.append(Path(repo).expanduser() / ".orch_env")
    candidates.append(INSTALL_DIR / ".orch_env")
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(str(path))
    return loaded


def _repo_for_env(args) -> str:
    """The repo whose .orch_env should apply — from --repo, or the checkpoint on resume."""
    if args.resume and args.state and Path(args.state).is_file():
        try:
            return json.loads(Path(args.state).read_text(encoding="utf-8")).get("repository", args.repo)
        except (OSError, ValueError):
            pass
    return args.repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-agent coding orchestrator over OpenRouter.")
    parser.add_argument("--task", "-t", help="The software-engineering task to perform (omit when --resume).")
    parser.add_argument("--repo", "-r", default=".", help="Path to the target repository (default: cwd).")
    parser.add_argument(
        "--workflow",
        "-w",
        choices=sorted(WORKFLOWS),
        help="Force a workflow instead of letting the router choose.",
    )
    parser.add_argument("--max-iterations", type=int, default=None, help="Max executor/reviewer passes.")
    parser.add_argument("--no-router", action="store_true", help="Skip the router; use the default workflow.")
    parser.add_argument("--skills", metavar="A,B", help="Extra skill names to inject (comma-separated).")
    parser.add_argument("--default-prompt", metavar="TEXT", help="Guidance injected into every agent.")
    pr = parser.add_mutually_exclusive_group()
    pr.add_argument("--open-pr", dest="open_pr", action="store_true", default=None,
                    help="Force opening a PR after review passes.")
    pr.add_argument("--no-pr", dest="open_pr", action="store_false",
                    help="Never open a PR, even if the workflow would.")
    parser.add_argument("--state", metavar="PATH", help="Checkpoint file: state is saved after each phase.")
    parser.add_argument("--resume", action="store_true", help="Continue an interrupted run from --state.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress the live agent-activity stream.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose (DEBUG) logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.WARNING)

    if args.resume and not args.state:
        print("error: --resume requires --state PATH", file=sys.stderr)
        return 2
    if not args.resume and not args.task:
        print("error: --task is required (unless resuming with --resume --state PATH)", file=sys.stderr)
        return 2

    # Load .orch_env files (project-first) BEFORE reading config from the env.
    loaded = load_env_files(_repo_for_env(args))
    if loaded and not args.quiet:
        print(f"config: loaded {', '.join(loaded)}", file=sys.stderr)

    config = OrchestratorConfig.from_env()
    if args.max_iterations is not None:
        config.max_iterations = args.max_iterations
    if args.no_router:
        config.use_router = False
    if args.skills:
        config.skills = config.skills + [s.strip() for s in args.skills.split(",") if s.strip()]
    if args.default_prompt is not None:
        config.default_prompt = args.default_prompt
    if args.open_pr is not None:
        config.open_pr = args.open_pr

    # Live agent narrative goes to stderr; stdout is reserved for the result.
    emit = null_sink if args.quiet else ConsoleSink(sys.stderr)

    try:
        orchestrator = Orchestrator(config=config, emit=emit)
    except Exception as exc:  # noqa: BLE001 - most likely a missing API key
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = orchestrator.run(
        task=args.task,
        repository=args.repo,
        workflow=args.workflow,
        checkpoint=args.state,
        resume=args.resume,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_human(result)

    return 0 if result.status == "PASS" else 1


def _print_human(result) -> None:
    line = "=" * 70
    print(f"\n{line}")
    print(f"STATUS:    {result.status}")
    print(f"WORKFLOW:  {result.workflow}")
    print(f"ITERATIONS:{result.iterations}")
    if result.pull_request:
        print(f"PULL REQUEST: {result.pull_request}")
    print(line)
    if result.modified_files:
        print("MODIFIED FILES:")
        for f in result.modified_files:
            print(f"  - {f}")
    print("\nSUMMARY:")
    print(result.summary or "(none)")
    if result.review and result.review.issues:
        print("\nOUTSTANDING ISSUES:")
        for issue in result.review.issues:
            print(f"  [{issue.severity}] {issue.file}: {issue.description}")
    if result.error:
        print(f"\nERROR: {result.error}")
    print(line)


if __name__ == "__main__":
    raise SystemExit(main())
