"""Pure validator for CodeTour `.tour` files (the Microsoft CodeTour JSON format).

A `.tour` file is a guided, step-by-step walkthrough anchored to real files and
lines. sigma generates these via Claude (see cli/learn.py); this module verifies
that what the agent produced actually anchors to the repo — every referenced file
exists, every line number is in range, every text pattern is present — so a tour
never points at a phantom location.

Pure logic: the only I/O is reading the anchored files under `repo_root`. Returns
a list of human-readable problems (empty list == valid). Testable with a fake repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def validate_tour(data: dict, repo_root: Path) -> List[str]:
    """Validate a parsed `.tour` dict against the repository. Empty list = valid."""
    problems: List[str] = []

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        problems.append("missing or empty 'title'")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("'steps' must be a non-empty list")
        return problems  # nothing more to check without steps

    for i, step in enumerate(steps):
        problems.extend(_validate_step(i, step, repo_root))
    return problems


def _validate_step(index: int, step: object, repo_root: Path) -> List[str]:
    """Validate one tour step. `index` is 0-based; messages report it 1-based."""
    n = index + 1
    out: List[str] = []
    if not isinstance(step, dict):
        return [f"step {n}: not an object"]

    description = step.get("description")
    if not isinstance(description, str) or not description.strip():
        out.append(f"step {n}: missing or empty 'description'")

    file_rel = step.get("file")
    if file_rel is None:
        # A directory step or a description-only step is allowed; nothing to anchor.
        return out

    if not isinstance(file_rel, str) or not file_rel.strip():
        out.append(f"step {n}: 'file' must be a non-empty string")
        return out

    target = (repo_root / file_rel)
    if not target.is_file():
        out.append(f"step {n}: file not found: {file_rel}")
        return out  # can't check line/pattern against a missing file

    try:
        lines = target.read_text(errors="replace").splitlines()
    except OSError as exc:
        return out + [f"step {n}: cannot read {file_rel}: {exc}"]

    line = step.get("line")
    if line is not None:
        if not isinstance(line, int) or isinstance(line, bool):
            out.append(f"step {n}: 'line' must be an integer")
        elif line < 1 or line > len(lines):
            out.append(
                f"step {n}: line {line} out of range for {file_rel} "
                f"(1..{len(lines)})"
            )

    pattern = step.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str) or not pattern:
            out.append(f"step {n}: 'pattern' must be a non-empty string")
        elif not any(pattern in ln for ln in lines):
            out.append(f"step {n}: pattern not found in {file_rel}: {pattern!r}")

    return out
