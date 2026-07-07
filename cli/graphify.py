"""Detect, install, and consume graphify for `sigma learn`.

graphify (https://github.com/safishamsi/graphify) turns a repo into a queryable
knowledge graph via local tree-sitter extraction (free, no API key for code) plus
optional LLM semantic links for docs. sigma does NOT import it — graphify requires
Python 3.10+ and sigma stays on the 3.9 floor. Instead sigma SHELLS OUT to a
standalone `graphify` binary installed in its own isolated environment via
`uv tool install graphifyy` (or pipx/pip). This is the same pattern sigma already
uses for `claude`/`gemini`/`codex`/`rtk` — a subprocess, never an import — so the
3.9 constraint is untouched.

`sigma learn` builds the graph (incremental `--update`) and injects graphify's
`GRAPH_REPORT.md` into the learn agent's prompt, grounding ARCHITECTURE.md + the
CodeTour in extracted structure. Everything here is fail-safe: graphify absent or a
build failure degrades to a plain learn (never crashes), and the install is
confirm-gated + idempotent (RTK/caveman shape). All lookups and spawns are injected
so tests never install anything or spawn a real process.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

# Upstream package name on PyPI (the import name would be `graphify`, but the
# distribution is `graphifyy`). Install in an isolated 3.10+ env, never as a dep.
_PKG = "graphifyy"

# graphify writes its artifacts here, relative to the extracted root.
_OUT_DIR = "graphify-out"
_REPORT_NAME = "GRAPH_REPORT.md"

# Default cap (chars) on the injected report block, so a huge graph can't blow the
# learn prompt — same discipline as skills_recall.render_recall_block's limit.
_DEFAULT_REPORT_CAP = 6000


def _default_spawn(argv: List[str]) -> int:
    """Run a command interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def graphify_status(which: Optional[Callable] = None) -> Dict:
    """Report {installed} — whether a `graphify` binary is on PATH."""
    which = which or shutil.which
    return {"installed": which("graphify") is not None}


_HOOK_MARKER = "graphify"


def graphify_hook_status(root: Path, which: Optional[Callable] = None) -> Dict:
    """Report {installed} — whether graphify's post-commit hook is in this repo.

    True when `root/.git/hooks/post-commit` exists and mentions graphify (the hook
    graphify writes embeds an interpreter path + a `graphify` invocation). Fail-safe:
    no `.git`, no hook, or an unreadable file → {"installed": False}. Never raises.
    `which` is accepted for signature symmetry with the other status fns (unused).
    """
    hook = root / ".git" / "hooks" / "post-commit"
    try:
        if not hook.is_file():
            return {"installed": False}
        return {"installed": _HOOK_MARKER in hook.read_text()}
    except OSError:
        return {"installed": False}


def install_graphify(
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Install graphify into an isolated environment. Best-effort, ordered.

    Prefers `uv tool install` (isolated, puts the CLI on PATH), then `pipx install`
    (same isolation), then `pip install --user` as a last resort. Returns True on
    the first installer that exits 0.
    """
    which = which or shutil.which
    spawn = spawn or _default_spawn

    if which("uv"):
        return spawn(["uv", "tool", "install", _PKG]) == 0
    if which("pipx"):
        return spawn(["pipx", "install", _PKG]) == 0
    return spawn([sys.executable, "-m", "pip", "install", "--user", _PKG]) == 0


def setup_graphify(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Confirm-gated, idempotent install. Returns True if it changed state.

    - Already installed → no-op (returns False).
    - Otherwise → confirm, then install. The user must approve before anything is
      installed (mirrors setup_rtk / setup_caveman).
    """
    status_fn = status_fn or graphify_status
    confirm = confirm or (lambda msg: False)
    st = status_fn()

    if st.get("installed"):
        return False  # already good

    if not confirm(
        "Install graphify (codebase knowledge-graph engine for `sigma learn`)?"
    ):
        return False

    return install_graphify(which=which, spawn=spawn)


def build_extract_argv(root: Path) -> List[str]:
    """argv to (re)extract the graph for `root` incrementally.

    `--update` re-extracts only changed files, so re-running `sigma learn` on an
    already-graphed repo is cheap. Run with cwd=root, so the target is ".".
    """
    return ["graphify", "extract", ".", "--update"]


def report_block(root: Path, cap: int = _DEFAULT_REPORT_CAP) -> str:
    """Return graphify's GRAPH_REPORT.md as a labeled prompt block, or "".

    Fail-safe: missing file, unreadable path, or a `graphify-out` that isn't a
    directory all yield "" so the learn prompt is byte-identical to the no-graph
    case. Oversized reports are truncated to `cap` chars with a notice.
    """
    report = root / _OUT_DIR / _REPORT_NAME
    try:
        if not report.is_file():
            return ""
        text = report.read_text()
    except OSError:
        return ""
    if not text.strip():
        return ""

    truncated = False
    if len(text) > cap:
        text = text[:cap]
        truncated = True

    lines = [
        "### codebase knowledge graph (graphify)",
        "The following is an extracted dependency-graph report for this repo "
        "(god-nodes, communities, surprising connections). Use it to ground the "
        "architecture map and tour in real structure:",
        "",
        text.rstrip(),
    ]
    if truncated:
        lines.append("\n[graph report truncated for length]")
    return "\n".join(lines)
