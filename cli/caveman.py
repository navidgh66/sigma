"""Detect, install, and activate the caveman terse-output mode for Claude Code.

Caveman is an optional Claude Code plugin (from the `caveman` marketplace) plus a
SessionStart hook that injects an ultra-compressed "speak like caveman" ruleset —
cutting ~75% of output tokens while keeping full technical accuracy. Because
installing it adds a marketplace and registers a hook in the GLOBAL
~/.claude/settings.json (shared state), sigma NEVER installs or activates caveman
without explicit confirmation — `setup_caveman` is confirm-gated and idempotent
(no-ops when caveman is already active).

This mirrors cli/rtk.py exactly: all process spawning and lookups are injectable,
so tests never install anything or modify the real settings.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

# Upstream marketplace + plugin identifiers.
_MARKETPLACE = "JuliusBrussee/caveman"
_PLUGIN = "caveman@caveman"
_ADD_MARKETPLACE = ["claude", "plugin", "marketplace", "add", _MARKETPLACE]
_INSTALL_PLUGIN = ["claude", "plugin", "install", _PLUGIN]


def _default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _default_plugins_path() -> Path:
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def _default_spawn(argv: List[str]) -> int:
    """Run a command interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def _hook_active(settings_path: Path) -> bool:
    """True if settings.json registers a caveman command in any hook."""
    if not settings_path.exists():
        return False
    try:
        data = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    return "caveman" in json.dumps(data.get("hooks", {}))


def _plugin_installed(plugins_path: Path) -> bool:
    """True if installed_plugins.json lists a caveman plugin."""
    if not plugins_path.exists():
        return False
    try:
        data = json.loads(plugins_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    return "caveman" in json.dumps(data.get("plugins", {}))


def caveman_status(
    which: Optional[Callable] = None,
    settings_path: Optional[Path] = None,
    plugins_path: Optional[Path] = None,
) -> Dict:
    """Report {claude_cli, installed, hook_active}.

    - claude_cli: the `claude` binary is on PATH (needed to install the plugin).
    - installed: the caveman plugin is recorded in installed_plugins.json.
    - hook_active: a caveman command is registered in settings.json hooks.
    """
    which = which or shutil.which
    settings_path = settings_path or _default_settings_path()
    plugins_path = plugins_path or _default_plugins_path()

    return {
        "claude_cli": which("claude") is not None,
        "installed": _plugin_installed(plugins_path),
        "hook_active": _hook_active(settings_path),
    }


def install_caveman(spawn: Optional[Callable] = None) -> bool:
    """Add the caveman marketplace and install the plugin via the `claude` CLI."""
    spawn = spawn or _default_spawn
    added = spawn(_ADD_MARKETPLACE) == 0
    installed = spawn(_INSTALL_PLUGIN) == 0
    return added and installed


def setup_caveman(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Confirm-gated, idempotent install. Returns True if it changed state.

    - Already active (installed + hook) → no-op (returns False).
    - `claude` CLI missing → can't install → no-op (returns False).
    - Otherwise → confirm, then install the plugin (which registers its hook).
    The user must approve before anything touches the global plugin/settings state.
    """
    status_fn = status_fn or caveman_status
    confirm = confirm or (lambda msg: False)
    st = status_fn()

    if st.get("installed") and st.get("hook_active"):
        return False  # already good

    if not st.get("claude_cli"):
        return False  # no claude CLI to install with — nothing we can do

    if not confirm(
        "Install caveman terse-output mode (~75% fewer output tokens) for Claude Code?"
    ):
        return False

    return install_caveman(spawn=spawn)
