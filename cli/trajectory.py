"""Agent trajectory capture — observability over what agents actually did.

The Google "New SDLC" paper makes the point that without observability there is
no way to tell whether an agent is doing well or quietly drifting. Sigma's loop
and hermes already record *outcomes* (events.jsonl) and *cost* (costs.jsonl).
This module records the *trajectory*: one append-only step per agent run (role,
model, ok, duration), so a human can audit how a result was reached, not just
what it was.

Same discipline as `events.py` / `cost.py`:
  - pure: no clock, no subprocess — the caller passes `ts`;
  - append-only JSONL (`trajectory.jsonl`) in the spec workspace;
  - the read model is lenient (corrupt lines skipped, missing file → empty);
  - `summarize` is a pure projection (deterministic, testable).

`AgentRunner` emits a step dict via an injected `trajectory_sink`; `make_sink`
builds a workspace-bound sink that stamps each step with a run timestamp. The
sink is best-effort — a write failure is swallowed so observability never breaks
a run (the inverse of a hard gate).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

TRAJECTORY_FILENAME = "trajectory.jsonl"


@dataclass
class TrajectoryStep:
    role: str
    model: Optional[str] = None
    ok: bool = True
    returncode: int = 0
    error: Optional[str] = None
    output_chars: int = 0
    duration_s: float = 0.0
    ts: Optional[str] = None
    # REAL measured usage (from claude --output-format json envelopes, via
    # AgentRunner telemetry). None = not measured (pre-telemetry steps, codex
    # runs, parse failures) — never fabricated.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    cost_usd: Optional[float] = None


def trajectory_path(workspace: Path) -> Path:
    return workspace / TRAJECTORY_FILENAME


def _opt_int(value) -> Optional[int]:
    """Optional token count: numeric → int, anything else (incl. bool) → None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def build_step(raw: dict, ts: Optional[str] = None) -> TrajectoryStep:
    """Build a TrajectoryStep from a runner's step dict (caller passes `ts`)."""
    raw = raw or {}
    cost = raw.get("cost_usd")
    return TrajectoryStep(
        role=str(raw.get("role", "agent")),
        model=raw.get("model"),
        ok=bool(raw.get("ok", True)),
        returncode=int(raw.get("returncode", 0) or 0),
        error=raw.get("error"),
        output_chars=int(raw.get("output_chars", 0) or 0),
        duration_s=float(raw.get("duration_s", 0.0) or 0.0),
        ts=ts if ts is not None else raw.get("ts"),
        input_tokens=_opt_int(raw.get("input_tokens")),
        output_tokens=_opt_int(raw.get("output_tokens")),
        cache_read_tokens=_opt_int(raw.get("cache_read_tokens")),
        cache_creation_tokens=_opt_int(raw.get("cache_creation_tokens")),
        cost_usd=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
    )


def append_step(workspace: Path, step: TrajectoryStep) -> Path:
    """Append one step as a JSONL line, creating the workspace if needed."""
    workspace.mkdir(parents=True, exist_ok=True)
    path = trajectory_path(workspace)
    with path.open("a") as fh:
        fh.write(json.dumps(asdict(step), sort_keys=True) + "\n")
    return path


def read_steps(workspace: Path) -> List[TrajectoryStep]:
    """Read all steps. Corrupt/non-JSON lines are skipped (lenient read-model)."""
    path = trajectory_path(workspace)
    if not path.exists():
        return []
    out: List[TrajectoryStep] = []
    try:
        text = path.read_text()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict) or "role" not in data:
            continue
        out.append(build_step(data, ts=data.get("ts")))
    return out


def make_sink(workspace: Path, ts: Optional[str] = None) -> Callable[[dict], None]:
    """Return a sink that appends each runner step dict to the workspace trajectory.

    Best-effort: a write failure (read-only fs, blocked path) is swallowed so the
    agent run is never broken by observability. Each step is stamped with `ts`.
    """

    def sink(raw: dict) -> None:
        try:
            append_step(workspace, build_step(raw, ts=ts))
        except OSError:
            pass

    return sink


def counting_sink(base: Callable[[dict], None]):
    """Wrap a sink so measured usage also accumulates in-memory for THIS run.

    Returns `(sink, totals)` where `totals` is a live dict
    `{"tokens": int, "cost_usd": float}` summing every token dimension across
    the steps the wrapped sink sees. The trajectory file is append-only across
    runs, so a caller that wants "this run's real cost" (e.g. cmd_loop's ledger
    record) counts here instead of re-reading and mis-attributing old steps.
    Non-numeric fields are skipped — absent telemetry leaves totals at zero.
    """
    totals = {"tokens": 0, "cost_usd": 0.0}

    def sink(raw: dict) -> None:
        base(raw)
        raw = raw or {}
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"):
            v = raw.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                totals["tokens"] += int(v)
        cost = raw.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            totals["cost_usd"] += float(cost)

    return sink, totals


# --------------------------------------------------------------------------- #
# Projection
# --------------------------------------------------------------------------- #
@dataclass
class TrajectorySummary:
    total: int = 0
    failures: int = 0
    by_role: Dict[str, int] = field(default_factory=dict)
    by_model: Dict[str, int] = field(default_factory=dict)
    total_duration_s: float = 0.0

    def render(self) -> str:
        if self.total == 0:
            return "# trajectory\n\nNo agent steps recorded yet."
        lines = [
            "# trajectory",
            "",
            f"**{self.total} step(s)**, {self.failures} failed, "
            f"{self.total_duration_s:.1f}s total agent time.",
            "",
            "## By role",
            "",
        ]
        for role in sorted(self.by_role, key=lambda r: self.by_role[r], reverse=True):
            lines.append(f"- **{role}**: {self.by_role[role]} step(s)")
        if self.by_model:
            lines += ["", "## By model", ""]
            for model in sorted(self.by_model, key=lambda m: self.by_model[m], reverse=True):
                lines.append(f"- **{model or '(default)'}**: {self.by_model[model]} step(s)")
        return "\n".join(lines)


def summarize(steps: List[TrajectoryStep]) -> TrajectorySummary:
    """Pure projection: fold steps into counts + per-role/model tallies + duration."""
    summary = TrajectorySummary()
    for s in steps:
        summary.total += 1
        if not s.ok:
            summary.failures += 1
        summary.by_role[s.role] = summary.by_role.get(s.role, 0) + 1
        key = s.model or ""
        summary.by_model[key] = summary.by_model.get(key, 0) + 1
        summary.total_duration_s += s.duration_s
    summary.total_duration_s = round(summary.total_duration_s, 3)
    return summary


# --------------------------------------------------------------------------- #
# Efficiency report (real, measured signals only — no token estimate)
# --------------------------------------------------------------------------- #
# Real signals only. Cycle steps (role="cycle", ok=verified — appended by
# cmd_loop after run_loop returns) give a true pass rate; per-role step counts
# give a true escalation rate. Token usage IS real when present: AgentRunner
# telemetry parses `claude -p --output-format json` result envelopes and stamps
# measured input/output/cache tokens (+cost_usd) onto steps — the report shows a
# token axis only for steps that actually carry measurements, and keeps the
# honest "no data" caveat otherwise (a static estimate must never wear a
# measured metric's clothes — that guess lives in `sigma cost`).
CYCLE_ROLE = "cycle"
ESCALATION_ROLES = ("logic", "advisor", "test-writer", "simplifier")


def efficiency_report(steps: List[TrajectoryStep]) -> str:
    """Render sigma's own cost-efficiency signals from REAL trajectory data.

    Leads with cycle pass rate (from role="cycle" steps, appended once per
    completed loop cycle — verified/not, distinct from a subprocess crash) and
    escalation rate (logic/advisor/test-writer/simplifier steps ÷ implementer
    steps — how often the expensive axes fire). Also reports the crash rate
    (subprocess exit failures across ALL roles) with an explicit label that it is
    NOT the same as a verify-fail — a verifier that returns `VERDICT: FAIL` still
    exits 0 (crash rate and verify-fail rate are genuinely different signals).
    Never raises: empty input renders a "no data yet" line, and each section is
    independently guarded against division by zero.
    """
    if not steps:
        return "# sigma efficiency\n\nNo trajectory data yet. Run `sigma loop --execute` first."

    cycle_steps = [s for s in steps if s.role == CYCLE_ROLE]
    lines = ["# sigma efficiency", ""]

    if cycle_steps:
        passed = sum(1 for s in cycle_steps if s.ok)
        rate = passed / len(cycle_steps)
        lines += [
            f"**Cycle pass rate: {rate:.0%}** ({passed}/{len(cycle_steps)} verified cycles).",
            "",
        ]
    else:
        lines += ["No completed loop cycles recorded yet (no `role=\"cycle\"` steps).", ""]

    summary = summarize(steps)
    implementer_n = summary.by_role.get("implementer", 0)
    escalation_n = sum(summary.by_role.get(r, 0) for r in ESCALATION_ROLES)
    if implementer_n > 0:
        esc_rate = escalation_n / implementer_n
        lines += [
            f"**Escalation rate: {esc_rate:.0%}** ({escalation_n} logic/advisor/test-writer/"
            f"simplifier step(s) per {implementer_n} implementer step(s)).",
            "",
        ]
    else:
        lines += ["No implementer steps recorded yet — escalation rate not computable.", ""]

    non_cycle = [s for s in steps if s.role != CYCLE_ROLE]
    if non_cycle:
        crashes = sum(1 for s in non_cycle if not s.ok)
        crash_rate = crashes / len(non_cycle)
        lines += [
            f"**Crash rate: {crash_rate:.0%}** ({crashes}/{len(non_cycle)} agent step(s) exited "
            "non-zero). This is subprocess failure, NOT verification failure — a verifier "
            "that returns `VERDICT: FAIL` still exits 0 and counts as a non-crash here.",
            "",
        ]

    measured = [
        s for s in non_cycle
        if any(v is not None for v in (s.input_tokens, s.output_tokens,
                                       s.cache_read_tokens, s.cache_creation_tokens))
    ]
    if measured:
        total_tokens = sum(
            (s.input_tokens or 0) + (s.output_tokens or 0)
            + (s.cache_read_tokens or 0) + (s.cache_creation_tokens or 0)
            for s in measured
        )
        total_cost = sum(s.cost_usd or 0.0 for s in measured)
        cost_note = f", ~${total_cost:.2f}" if total_cost > 0 else ""
        lines += [
            f"**Measured tokens: {total_tokens:,}**{cost_note} across {len(measured)} "
            f"agent step(s) — REAL usage from `claude --output-format json` result "
            "envelopes (steps without telemetry are excluded, never estimated).",
        ]
    else:
        lines += [
            "_No measured token data yet: steps carry real usage only when run with "
            "AgentRunner telemetry (`claude -p --output-format json`) — see `sigma cost` "
            "for the honestly-labeled estimate instead._",
        ]
    return "\n".join(lines)
