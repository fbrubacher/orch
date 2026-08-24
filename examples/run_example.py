"""Minimal example of the public API.

The caller only states *what* it wants and *where*; the orchestrator handles
routing, planning, execution, validation and review internally.

Run with:  python examples/run_example.py
"""

from __future__ import annotations

import os
import sys

# Make the project root importable when run as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".orch_env"))
except ImportError:
    pass

from orchestrator import Orchestrator
from orchestrator.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    orchestrator = Orchestrator()
    result = orchestrator.run(
        task="Add a function `slugify(text: str) -> str` in a new module `text_utils.py` "
        "with a matching pytest test, and make the tests pass.",
        repository=".",
    )
    print("status:", result.status)
    print("workflow:", result.workflow)
    print("modified:", result.modified_files)
    print("summary:\n", result.summary)


if __name__ == "__main__":
    main()
