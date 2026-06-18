"""Detect, install, and activate RTK (the Rust Token Killer) for Claude Code.

RTK is an optional token-saving bash proxy. `rtk init -g` installs a PreToolUse
hook into the GLOBAL ~/.claude/settings.json and rewrites bash commands to save
60-90% tokens. Because that touches global, shared state, sigma NEVER installs or
activates RTK without explicit confirmation — `setup_rtk` is confirm-gated and
idempotent (no-ops when RTK is already active).

All process spawning and lookups are injectable so tests never install anything
or modify the real settings.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Upstream install entrypoints.
_BREW = ["brew", "install", "rtk"]
_CURL = [
    "sh",
    "-c",
    "curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh",
]
_ACTIVATE = ["rtk", "init", "-g"]


def _default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


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


def _hook_active(settings_path: Path) -> bool:
    """True if settings.json registers an rtk command in any hook."""
    if not settings_path.exists():
        return False
    try:
        data = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    return "rtk" in json.dumps(data.get("hooks", {}))


def rtk_status(
    which: Optional[Callable] = None,
    run: Optional[Callable] = None,
    settings_path: Optional[Path] = None,
) -> Dict:
    """Report {installed, gain_ok, hook_active}.

    `gain_ok` distinguishes the real RTK from a name-collision binary by checking
    that `rtk gain` succeeds (per the project's RTK guidance).
    """
    which = which or shutil.which
    run = run or _default_run
    settings_path = settings_path or _default_settings_path()

    installed = which("rtk") is not None
    gain_ok = False
    if installed:
        code, _ = run(["rtk", "gain"])
        gain_ok = code == 0
    return {
        "installed": installed,
        "gain_ok": gain_ok,
        "hook_active": _hook_active(settings_path) if installed else False,
    }


def install_rtk(which: Optional[Callable] = None, spawn: Optional[Callable] = None) -> bool:
    """Install RTK: Homebrew if available, else the upstream curl script."""
    which = which or shutil.which
    spawn = spawn or _default_spawn
    argv = _BREW if which("brew") else _CURL
    return spawn(argv) == 0


def activate_rtk(spawn: Optional[Callable] = None) -> bool:
    """Activate RTK for Claude Code via `rtk init -g`. Modifies global settings."""
    spawn = spawn or _default_spawn
    return spawn(_ACTIVATE) == 0


def setup_rtk(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Confirm-gated, idempotent install+activate. Returns True if it changed state.

    - Fully active → no-op (returns False).
    - Installed but inactive → confirm, then activate only.
    - Not installed → confirm, then install + activate.
    The user must approve before anything touches the global settings.json.
    """
    status_fn = status_fn or rtk_status
    confirm = confirm or (lambda msg: False)
    st = status_fn()

    if st.get("installed") and st.get("hook_active") and st.get("gain_ok"):
        return False  # already good

    if not st.get("installed"):
        if not confirm("Install RTK (60-90% token saver) and activate it for Claude?"):
            return False
        install_rtk(which=which, spawn=spawn)
        activate_rtk(spawn=spawn)
        return True

    # Installed but not active.
    if not confirm("Activate RTK for Claude Code now (modifies ~/.claude/settings.json)?"):
        return False
    activate_rtk(spawn=spawn)
    return True
