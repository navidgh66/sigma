"""Detect + install the SessionStart hook that surfaces the learn pointer.

A Claude Code SessionStart hook runs a command at session start and injects its
stdout as additionalContext. Here that command is `sigma session-context`, which
prints the pointer to this repo's learn artifacts (see cli/session_context.py) so
every new session is nudged to read them before deep work.

The hook is written into the PROJECT .claude/settings.json (repo-scoped — it only
fires in, and reads, this repo). Because settings.json is shared state, the write
is confirm-gated and idempotent, and uses an IMMUTABLE merge (new dict, every
other key preserved) — the exact shape of cli/statusline.py. All I/O is injectable
so tests never touch a real settings.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

# The command our hook runs. `sigma session-context` always exits 0 (a hook must
# never break a session) and prints the learn pointer to stdout.
_HOOK_COMMAND = "sigma session-context"


def _default_settings_path() -> Path:
    """Project-scoped settings file (repo-relative)."""
    return Path(".claude") / "settings.json"


def _read_settings(settings_path: Path) -> Optional[Dict]:
    if not settings_path.exists():
        return None
    try:
        return json.loads(settings_path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _session_start_commands(data: Dict) -> List[str]:
    """Flatten every command string registered under hooks.SessionStart."""
    cmds: List[str] = []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    entries = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    if not isinstance(entries, list):
        return cmds
    for entry in entries:
        inner = entry.get("hooks") if isinstance(entry, dict) else None
        if isinstance(inner, list):
            for h in inner:
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    cmds.append(h["command"])
    return cmds


def _is_configured(data: Optional[Dict]) -> bool:
    if not isinstance(data, dict):
        return False
    return any(_HOOK_COMMAND in c for c in _session_start_commands(data))


def install_payload(data: Dict) -> Dict:
    """Return a NEW settings dict with our SessionStart hook merged in.

    Immutable: builds fresh dicts/lists, never mutates `data`. Appends our entry
    to any existing SessionStart hooks rather than replacing them.
    """
    base = dict(data) if isinstance(data, dict) else {}
    hooks = dict(base.get("hooks") or {})
    existing = list(hooks.get("SessionStart") or [])
    our_entry = {"hooks": [{"type": "command", "command": _HOOK_COMMAND}]}
    hooks["SessionStart"] = existing + [our_entry]
    base["hooks"] = hooks
    return base


def session_hook_status(settings_path: Optional[Path] = None) -> Dict:
    """Report {configured}: True if our SessionStart hook is already registered."""
    settings_path = settings_path or _default_settings_path()
    return {"configured": _is_configured(_read_settings(settings_path))}


def install_session_hook(
    settings_path: Optional[Path] = None,
    writer: Optional[Callable[[Path, Dict], bool]] = None,
) -> bool:
    """Write the SessionStart hook into settings.json, preserving other keys."""
    settings_path = settings_path or _default_settings_path()
    writer = writer or _write_settings
    data = _read_settings(settings_path) or {}
    return writer(settings_path, install_payload(data))


def _write_settings(settings_path: Path, data: Dict) -> bool:
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(data, indent=2) + "\n")
        return True
    except OSError:
        return False


def setup_session_hook(
    status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    settings_path: Optional[Path] = None,
    writer: Optional[Callable[[Path, Dict], bool]] = None,
) -> bool:
    """Confirm-gated, idempotent install. Returns True if it changed state.

    Already configured → no-op. Otherwise confirm, then write the hook. The user
    must approve before anything touches the project settings.json.
    """
    status_fn = status_fn or (lambda: session_hook_status(settings_path))
    confirm = confirm or (lambda msg: False)

    if status_fn().get("configured"):
        return False

    if not confirm(
        "Add a SessionStart hook so new Claude Code sessions read this repo's "
        "learn artifacts (ARCHITECTURE.md / tour)?"
    ):
        return False

    return install_session_hook(settings_path=settings_path, writer=writer)
