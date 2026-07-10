"""Detect and prompt ChatGPT sign-in for the codex CLI.

`codex exec` (research's gpt lane, `sigma loop --codex-verify`/`--codex-tdd`) is
subscription-backed via `codex login` (opens a browser, no API key). Because
that's an interactive OAuth flow, sigma never runs it without confirmation —
`setup_codex_login` is confirm-gated and idempotent (no-ops when already logged
in, mirroring `cli/rtk.py`'s shape).

All process spawning and lookups are injectable so tests never touch a real
codex session.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

_LOGIN = ["codex", "login"]
_STATUS = ["codex", "login", "status"]


def _default_run(argv: List[str]) -> Tuple[int, str]:
    """Run a command, capture (returncode, combined output)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _default_spawn(argv: List[str]) -> int:
    """Run a command interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def codex_login_status(
    which: Optional[Callable] = None,
    run: Optional[Callable] = None,
) -> Dict:
    """Report {installed, logged_in}.

    `logged_in` requires BOTH a zero exit code AND recognized "logged in" text
    in `codex login status`'s output — an unrecognized message (e.g. a future
    CLI wording change) defaults to not-logged-in, the safe/conservative read.
    """
    which = which or shutil.which
    run = run or _default_run

    installed = which("codex") is not None
    logged_in = False
    if installed:
        code, output = run(_STATUS)
        logged_in = code == 0 and "logged in" in output.lower()
    return {"installed": installed, "logged_in": logged_in}


def setup_codex_login(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Confirm-gated, idempotent sign-in. Returns True if it changed state.

    - Not installed → no-op, no prompt (nothing to log into).
    - Already logged in → no-op.
    - Installed, not logged in → confirm, then `codex login` (interactive,
      opens a browser). The user must approve before anything runs.
    """
    status_fn = status_fn or (lambda: codex_login_status(which=which))
    confirm = confirm or (lambda msg: False)
    spawn = spawn or _default_spawn
    st = status_fn()

    if not st.get("installed") or st.get("logged_in"):
        return False

    if not confirm(
        "Sign in to Codex now (opens browser, ChatGPT subscription — needed for "
        "sigma loop --codex-verify/--codex-tdd)?"
    ):
        return False

    return spawn(_LOGIN) == 0
