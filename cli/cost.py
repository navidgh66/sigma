"""Pure logic for sigma's cost loop — estimate before, measure after, sharpen next.

Heavy sigma ops (review's 3 axes, the profile walk, loop cycles, multi-model
research) burn tokens. This module closes a loop around that cost, mirroring the
lessons loop's philosophy:

  - estimate(op, inputs) → an advisory BEFORE the run: per-axis token estimate +
    a model-tier recommendation (cheap model for mechanical axes, strong model for
    reasoning axes), so the operator can steer the run;
  - record(...) → one append line for `sigma/costs.jsonl` AFTER the run (the caller
    passes the timestamp — projection stays deterministic, like `events.Event.ts`);
  - calibrate(rows) → adjust the token-per-unit factor from recent est-vs-actual
    deltas, so the estimate sharpens over time;
  - report(rows) → trends, per-op spend, biggest sinks, routing suggestions.

Fail-safe: a missing or garbage ledger falls back to static factors and never
blocks the op (the inverse of a hard gate, like gate-defaults-WAKE). Pure: no
subprocess, no clock; everything is injectable for tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Model tiers, cheapest → strongest. Recommendation maps an axis's reasoning load
# onto one of these (see performance.md's model-selection strategy).
TIER_CHEAP = "haiku"
TIER_MID = "sonnet"
TIER_STRONG = "opus"

# Static fallback: average tokens consumed per "unit of work" for an op, used when
# the ledger is empty or unreadable. A unit is op-specific (a file, an axis, a
# model). Deliberately rough — calibration replaces these as real data arrives.
_STATIC_TOKENS_PER_UNIT = {
    "review": 4000,    # per (axis × file) — 3 axes read the diff + profile
    "profile": 3000,   # per file walked
    "loop": 6000,      # per cycle (implement + verify + logic)
    "research": 8000,  # per model (full brief + findings)
}
_DEFAULT_TOKENS_PER_UNIT = 4000

# Which model tier each op's axes should lean on. Mechanical/style → cheap;
# reasoning/ML-logic → strong. `review` is per-axis (see _AXIS_TIER).
_AXIS_TIER = {
    "code": TIER_CHEAP,
    "ml-logic": TIER_STRONG,
    "system-logic": TIER_MID,
}
LEDGER_FILENAME = "costs.jsonl"


def ledger_path(project_root: Path) -> Path:
    """Where the append-only cost ledger lives for a project."""
    return project_root / "sigma" / LEDGER_FILENAME


# --------------------------------------------------------------------------- #
# Estimate
# --------------------------------------------------------------------------- #
@dataclass
class CostEstimate:
    """Advisory produced BEFORE a heavy op."""

    op: str
    units: int
    tokens_per_unit: float
    estimated_tokens: int
    routing: Dict[str, str] = field(default_factory=dict)
    calibrated: bool = False  # True if tokens_per_unit came from the ledger

    def render(self) -> str:
        """A compact advisory line for the CLI / slash command to print."""
        src = "calibrated" if self.calibrated else "static estimate"
        lines = [
            f"cost estimate [{self.op}]: ~{self.estimated_tokens:,} tokens "
            f"({self.units} unit(s) × {self.tokens_per_unit:,.0f}, {src})"
        ]
        if self.routing:
            routes = ", ".join(f"{k}→{v}" for k, v in self.routing.items())
            lines.append(f"  suggested routing: {routes}")
        return "\n".join(lines)


def routing_for(op: str) -> Dict[str, str]:
    """Recommend a model tier per axis/unit for an op."""
    if op == "review":
        return dict(_AXIS_TIER)
    if op == "profile":
        return {"walk": TIER_MID}
    if op == "loop":
        return {"implement": TIER_MID, "verify": TIER_MID, "logic": TIER_STRONG}
    if op == "research":
        return {"fan-out": TIER_MID}
    return {}


def estimate(
    op: str,
    units: int,
    rows: Optional[List[dict]] = None,
) -> CostEstimate:
    """Estimate token cost for `op` over `units` units of work.

    `rows` are prior ledger rows (from `read_ledger`); when present and usable,
    the per-unit factor is calibrated from them, else the static fallback is used.
    `units` is clamped to >= 0; a 0-unit op estimates 0 (e.g. empty diff).
    """
    units = max(0, units)
    factor, calibrated = _tokens_per_unit(op, rows or [])
    return CostEstimate(
        op=op,
        units=units,
        tokens_per_unit=factor,
        estimated_tokens=int(round(units * factor)),
        routing=routing_for(op),
        calibrated=calibrated,
    )


def _tokens_per_unit(op: str, rows: List[dict]) -> tuple:
    """Return (tokens_per_unit, calibrated?). Calibrate from the ledger if possible."""
    factor = calibrate(op, rows)
    if factor is not None:
        return factor, True
    return float(_STATIC_TOKENS_PER_UNIT.get(op, _DEFAULT_TOKENS_PER_UNIT)), False


def calibrate(op: str, rows: List[dict]) -> Optional[float]:
    """Tokens-per-unit for `op` from the ledger, or None if no usable rows.

    Uses a WEIGHTED factor — total tokens / total units across usable rows — so a
    large run counts proportionally more than a tiny one (an unweighted mean of
    per-row ratios over-weights small-run outliers). Skips rows with missing/zero
    units or non-numeric tokens (defensive against a hand-edited or partially
    written ledger). Returns None when nothing usable is found, so the caller falls
    back to the static factor (fail-safe).
    """
    total_tokens = 0.0
    total_units = 0.0
    for row in rows:
        if not isinstance(row, dict) or row.get("op") != op:
            continue
        units = row.get("units")
        tokens = row.get("tokens")
        if not isinstance(units, (int, float)) or not isinstance(tokens, (int, float)):
            continue
        if units <= 0 or tokens <= 0:
            continue
        total_tokens += float(tokens)
        total_units += float(units)
    if total_units <= 0:
        return None
    return total_tokens / total_units


# --------------------------------------------------------------------------- #
# Record
# --------------------------------------------------------------------------- #
def build_record(
    op: str,
    units: int,
    tokens: int,
    ts: str,
    estimated: Optional[int] = None,
    models: Optional[Dict[str, str]] = None,
) -> dict:
    """Build one ledger row (the caller passes `ts` — no clock here).

    `estimated` (the pre-flight estimate) is stored alongside the actual so a
    report can show est-vs-actual drift shrinking as calibration kicks in.
    """
    row: dict = {"ts": ts, "op": op, "units": units, "tokens": tokens}
    if estimated is not None:
        row["estimated"] = estimated
    if models:
        row["models"] = models
    return row


def append_ledger(ledger: Path, row: dict) -> Path:
    """Append one JSON row to the cost ledger (append-only, like events.jsonl)."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return ledger


def read_ledger(ledger: Path) -> List[dict]:
    """Read all rows from the ledger. Skips malformed lines (never raises).

    Fail-safe: a missing file → []; a garbage line → skipped, not fatal. This is
    what lets a corrupt ledger degrade to static estimates instead of blocking.
    """
    if not ledger.exists():
        return []
    rows: List[dict] = []
    try:
        text = ledger.read_text()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def report(rows: List[dict]) -> str:
    """Render a cost report: per-op totals, biggest sinks, est-vs-actual drift."""
    if not rows:
        return "# sigma cost\n\nNo cost data yet. Heavy ops record into `sigma/costs.jsonl`."

    by_op: Dict[str, Dict[str, float]] = {}
    total = 0
    for row in rows:
        op = str(row.get("op", "?"))
        tokens = row.get("tokens", 0)
        # Skip rows with non-numeric or non-positive tokens entirely — they must not
        # inflate the run count while contributing nothing to the token total.
        if not isinstance(tokens, (int, float)) or tokens <= 0:
            continue
        agg = by_op.setdefault(op, {"runs": 0, "tokens": 0.0, "est": 0.0, "est_runs": 0})
        agg["runs"] += 1
        agg["tokens"] += tokens
        total += tokens
        est = row.get("estimated")
        if isinstance(est, (int, float)):
            agg["est"] += est
            agg["est_runs"] += 1

    lines = ["# sigma cost", "", f"**Total recorded: ~{int(total):,} tokens** "
             f"across {len(rows)} run(s).", "", "## By operation", ""]
    for op in sorted(by_op, key=lambda o: by_op[o]["tokens"], reverse=True):
        agg = by_op[op]
        line = (f"- **{op}**: ~{int(agg['tokens']):,} tokens over {int(agg['runs'])} run(s)")
        if agg["est_runs"]:
            drift = agg["tokens"] - agg["est"]
            sign = "+" if drift >= 0 else ""
            line += f" (est drift {sign}{int(drift):,})"
        lines.append(line)
    lines += ["", "## Tips", "",
              "- Route mechanical axes to a cheap tier (`code`→haiku), reserve a "
              "strong tier for reasoning (`ml-logic`→opus).",
              "- Enable RTK to cut token overhead on dev ops; caveman trims output.",
              ""]
    return "\n".join(lines)
