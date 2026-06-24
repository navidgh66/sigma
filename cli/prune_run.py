"""`sigma prune` — surface loaded-but-unused MCP servers + plugins, disable reversibly.

The side-effectful half of prune. Pure inventory/usage/ranking live in
`cli/prune.py`; this module reads the real config files (`~/.claude/settings.json`,
`~/.claude.json`, the project `.mcp.json`), scans recent session transcripts for
actual tool/skill usage, builds the report, and — only on confirmation — writes a
**reversible disable** into settings.json via an immutable merge (new dict, every
other key preserved, exactly like cli/statusline.py). Disable is NEVER an uninstall.

Fail-safe throughout: unreadable settings → empty inventory + no write; missing
transcripts → usage unknown, which the pure layer treats conservatively as "used"
so nothing is pruned on absent evidence. All paths + readers are injectable so tests
never touch the real home dir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli import prune

# settings.json key sigma owns for reversible disables. Disabling a plugin =
# flipping its enabledPlugins entry to False (Claude Code's native mechanism).
_ENABLED_PLUGINS = "enabledPlugins"

# How many recent transcript files to scan for usage, and the lookback window.
_DEFAULT_TRANSCRIPT_FILES = 40


@dataclass
class PruneReport:
    candidates: List[prune.Candidate] = field(default_factory=list)
    freed_tokens: int = 0
    scanned_files: int = 0
    note: Optional[str] = None


# --------------------------------------------------------------------------- #
# default IO (all injectable)
# --------------------------------------------------------------------------- #
def _default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _default_claude_json_path() -> Path:
    return Path.home() / ".claude.json"


def _default_transcripts_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _read_json(path: Path) -> Optional[dict]:
    try:
        if not path.is_file():
            return None
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError, OSError):
        return None


def _write_settings(path: Path, data: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# transcript usage scan
# --------------------------------------------------------------------------- #
def scan_usage(
    transcripts_dir: Path,
    max_files: int = _DEFAULT_TRANSCRIPT_FILES,
    lister: Optional[Callable[[Path], List[Path]]] = None,
) -> tuple:
    """Return (tool_invocations, skill_refs, files_scanned) from recent transcripts.

    Reads the newest `max_files` *.jsonl transcripts and pulls every `tool_use`
    name plus the `skill`/`command` arg of any `Skill` invocation. Fail-safe: a
    missing dir or a garbled line is skipped, never fatal.
    """
    lister = lister or _default_lister
    files = lister(transcripts_dir)[:max_files]
    invocations: List[str] = []
    skill_refs: List[str] = []
    scanned = 0
    for f in files:
        try:
            text = f.read_text()
        except OSError:
            continue
        scanned += 1
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            _collect_from_record(obj, invocations, skill_refs)
    return invocations, skill_refs, scanned


def _default_lister(transcripts_dir: Path) -> List[Path]:
    if not transcripts_dir.exists():
        return []
    files = list(transcripts_dir.rglob("*.jsonl"))
    # newest first, so the lookback favors recent sessions
    return sorted(files, key=lambda p: _safe_mtime(p), reverse=True)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _collect_from_record(obj, invocations: List[str], skill_refs: List[str]) -> None:
    if not isinstance(obj, dict):
        return
    msg = obj.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if isinstance(name, str):
            invocations.append(name)
        if name == "Skill":
            inp = block.get("input")
            if isinstance(inp, dict):
                ref = inp.get("skill") or inp.get("command")
                if isinstance(ref, str):
                    skill_refs.append(ref)


# --------------------------------------------------------------------------- #
# build report
# --------------------------------------------------------------------------- #
def build_report(
    settings_path: Optional[Path] = None,
    claude_json_path: Optional[Path] = None,
    project_mcp_path: Optional[Path] = None,
    transcripts_dir: Optional[Path] = None,
    max_files: int = _DEFAULT_TRANSCRIPT_FILES,
    lister: Optional[Callable[[Path], List[Path]]] = None,
) -> PruneReport:
    """Inventory loaded items, score usage from transcripts, rank disable candidates."""
    settings = _read_json(settings_path or _default_settings_path())
    claude_json = _read_json(claude_json_path or _default_claude_json_path())
    project_mcp = _read_json(project_mcp_path) if project_mcp_path else None

    items = prune.parse_plugins(settings) + prune.parse_mcp_servers(claude_json, project_mcp)
    if not items:
        return PruneReport(note="nothing loaded to prune (no plugins or MCP servers found)")

    invocations, skill_refs, scanned = scan_usage(
        transcripts_dir or _default_transcripts_dir(), max_files=max_files, lister=lister
    )
    if scanned == 0:
        # No usage evidence → don't guess. Surface nothing (conservative: keep all).
        return PruneReport(
            scanned_files=0,
            note="no session transcripts found — skipping (won't prune without usage evidence)",
        )

    usage = prune.usage_counts(invocations, skill_refs, items)
    candidates = prune.rank_candidates(items, usage)
    return PruneReport(
        candidates=candidates,
        freed_tokens=prune.total_weight(candidates),
        scanned_files=scanned,
        note=None if candidates else "everything loaded was used recently — nothing to prune",
    )


# --------------------------------------------------------------------------- #
# reversible disable
# --------------------------------------------------------------------------- #
def disable_plugins(
    names: List[str],
    settings_path: Optional[Path] = None,
    writer: Optional[Callable[[Path, dict], bool]] = None,
) -> bool:
    """Flip the given plugins to disabled in settings.json (reversible, never uninstall).

    Immutable merge: a brand-new dict is written; every other settings key is
    preserved untouched (same discipline as cli/statusline.py). Re-enabling is just
    flipping the flag back — nothing is removed from disk.
    """
    settings_path = settings_path or _default_settings_path()
    writer = writer or _write_settings
    data = _read_json(settings_path) or {}
    if not isinstance(data, dict):
        data = {}
    enabled = dict(data.get(_ENABLED_PLUGINS) or {})
    for name in names:
        enabled[name] = False  # disable, do not delete the entry
    merged = {**data, _ENABLED_PLUGINS: enabled}
    return writer(settings_path, merged)
