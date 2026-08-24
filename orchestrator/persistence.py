"""Checkpoint persistence: save/load :class:`WorkflowState` as JSON.

Writes are atomic (temp file + rename) so an interrupted save never corrupts an
existing checkpoint.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .state import WorkflowState


def save_state(path: str | Path, state: WorkflowState) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state(path: str | Path) -> WorkflowState:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return WorkflowState.from_dict(data)
