"""wakeAgent gate: a cheap pluggable pre-check that skips work when nothing changed.

Inspired by the Hermes/NotebookLM "wakeAgent" pattern. Before sigma spends tokens
on a loop cycle or a hermes hop, it can run a user-supplied gate script. The
script prints a JSON line `{"wakeAgent": true|false}`; false means "nothing to do"
so the agent is skipped and zero tokens are spent.

Fail-safe by design: a missing gate, a spawn error, or unparseable output all
default to WAKE. A broken gate must never silently block real work — the inverse
of verdict parsing (which defaults to FAIL).

The spawn function is injected so tests never launch a real process.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

_GATE_KEY = "wakeAgent"


@dataclass
class GateResult:
    wake: bool
    reason: str


def _default_spawn(argv, cwd=None) -> Tuple[int, str]:
    """Run the gate script via argv (never the shell); capture (code, stdout)."""
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=30)
    return proc.returncode, (proc.stdout or "")


def _parse_wake(output: str) -> Optional[bool]:
    """Find a JSON object carrying wakeAgent in the output; None if not found."""
    for line in output.splitlines():
        line = line.strip()
        if not line or _GATE_KEY not in line:
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and _GATE_KEY in data:
            return bool(data[_GATE_KEY])
    return None


def run_gate(
    script: Optional[str],
    cwd: Optional[Path] = None,
    spawn: Callable = _default_spawn,
) -> GateResult:
    """Run the gate script and decide wake/skip.

    - No script → WAKE (gating is opt-in).
    - JSON `wakeAgent: false` → SKIP.
    - JSON `wakeAgent: true` → WAKE.
    - Unparseable output, spawn error → WAKE (fail-safe; never silently skip).
    """
    if not script:
        return GateResult(wake=True, reason="no gate configured")

    argv = shlex.split(script)
    try:
        _code, output = spawn(argv, cwd=cwd)
    except OSError as exc:
        return GateResult(wake=True, reason=f"gate failed to run ({exc}) — waking")

    decision = _parse_wake(output)
    if decision is None:
        return GateResult(wake=True, reason="gate output unparseable — waking (fail-safe)")
    if decision:
        return GateResult(wake=True, reason="gate: wakeAgent true")
    return GateResult(wake=False, reason="gate: wakeAgent false — skipping (0 tokens)")
