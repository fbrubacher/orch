"""Logging configuration for the orchestrator."""

from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down the very chatty HTTP library.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
