"""Load agent system prompts from the ``prompts/`` directory.

Prompts live in Markdown files so they can be iterated on independently of the
orchestration code and swapped without touching Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = _ROOT / "prompts"
SKILLS_DIR = _ROOT / "skills"


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def load_skill(name: str) -> str:
    return (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def compose(base: str, extra: str) -> str:
    """Append injected guidance (default prompt + skills) to a base system prompt."""
    extra = (extra or "").strip()
    if not extra:
        return base
    return f"{base}\n\n---\n\n# Additional operating guidance\n\n{extra}"


def available_skills() -> list[str]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md") if p.stem != "README")


def load_skills(names: list[str]) -> tuple[str, list[str]]:
    """Concatenate the named skills' text. Returns (text, missing_names).

    Missing skills are skipped (not fatal) and reported so the caller can warn.
    """
    parts: list[str] = []
    missing: list[str] = []
    for name in names:
        path = SKILLS_DIR / f"{name}.md"
        if path.exists():
            parts.append(load_skill(name))
        else:
            missing.append(name)
    return "\n\n".join(parts), missing
