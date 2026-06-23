"""Detect + install the ccstatusline status line for Claude Code.

ccstatusline (https://github.com/sirmalloc/ccstatusline) is a customizable status
line for the Claude Code CLI — model, git branch, token usage, session cost, etc.
It integrates by writing a `statusLine` command block into the GLOBAL
~/.claude/settings.json. Because that is shared state, sigma NEVER writes it
without explicit confirmation — `setup_statusline` is confirm-gated and idempotent
(no-ops when a statusLine is already configured).

Mirrors cli/caveman.py + cli/rtk.py: all process spawning and lookups are
injectable, so tests never install anything or modify the real settings.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

# The statusLine command we register. Uses npx so it works without a global
# install; ccstatusline self-manages a pinned version on first run.
_STATUSLINE_COMMAND = "npx -y ccstatusline@latest"
_STATUSLINE_BLOCK = {
    "type": "command",
    "command": _STATUSLINE_COMMAND,
    "padding": 0,
}


def _default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _default_spawn(argv: List[str]) -> int:
    """Run a command interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def _read_settings(settings_path: Path) -> Optional[Dict]:
    if not settings_path.exists():
        return None
    try:
        return json.loads(settings_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _statusline_configured(settings_path: Path) -> bool:
    """True if settings.json already defines a statusLine command."""
    data = _read_settings(settings_path)
    if not isinstance(data, dict):
        return False
    sl = data.get("statusLine")
    return isinstance(sl, dict) and bool(sl.get("command"))


def statusline_status(
    which: Optional[Callable] = None,
    settings_path: Optional[Path] = None,
) -> Dict:
    """Report {node_runtime, configured}.

    - node_runtime: an `npx` or `bunx` runner is on PATH (needed to run ccstatusline).
    - configured: settings.json already defines a statusLine command.
    """
    which = which or shutil.which
    settings_path = settings_path or _default_settings_path()
    return {
        "node_runtime": which("npx") is not None or which("bunx") is not None,
        "configured": _statusline_configured(settings_path),
    }


def install_statusline(
    settings_path: Optional[Path] = None,
    writer: Optional[Callable[[Path, Dict], bool]] = None,
) -> bool:
    """Write the statusLine block into settings.json, preserving other keys.

    Returns True on success. The writer is injectable for host-free tests.
    """
    settings_path = settings_path or _default_settings_path()
    writer = writer or _write_settings
    data = _read_settings(settings_path) or {}
    if not isinstance(data, dict):
        data = {}
    # Immutable update: new dict, don't mutate the loaded one.
    merged = {**data, "statusLine": dict(_STATUSLINE_BLOCK)}
    return writer(settings_path, merged)


def _write_settings(settings_path: Path, data: Dict) -> bool:
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
        return True
    except OSError:
        return False


def setup_statusline(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    settings_path: Optional[Path] = None,
    writer: Optional[Callable[[Path, Dict], bool]] = None,
) -> bool:
    """Confirm-gated, idempotent install. Returns True if it changed state.

    - Already configured → no-op (returns False).
    - No node runtime (npx/bunx) → can't run ccstatusline → no-op (returns False).
    - Otherwise → confirm, then write the statusLine block to settings.json.
    The user must approve before anything touches the global settings state.
    """
    status_fn = status_fn or statusline_status
    confirm = confirm or (lambda msg: False)
    st = status_fn()

    if st.get("configured"):
        return False  # already good

    if not st.get("node_runtime"):
        return False  # no npx/bunx to run ccstatusline with

    if not confirm(
        "Install the ccstatusline status line (model / branch / tokens / cost) for Claude Code?"
    ):
        return False

    return install_statusline(settings_path=settings_path, writer=writer)
