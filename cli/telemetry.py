"""Pure parsing for claude CLI result envelopes — real token/cost telemetry.

`claude -p --output-format json` wraps the agent's final text in a JSON result
envelope carrying REAL usage (input/output/cache tokens) and `total_cost_usd`.
This module extracts both so the trajectory can record measured tokens and the
cost ledger can finally calibrate from actuals instead of static factors (the
gap `cli/trajectory.py`'s efficiency report documents).

Same discipline as the other pure read-models:
  - no subprocess, no clock, no I/O — string in, dataclass out;
  - LENIENT: anything that isn't a well-formed envelope returns None, and the
    caller falls back to the plain-text path (telemetry must never break a run,
    the same law as a failing trajectory sink).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UsageEnvelope:
    """The agent's final text plus its measured usage."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: Optional[float] = None

    @property
    def total_tokens(self) -> int:
        """All billed token dimensions summed (input + output + both cache kinds)."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


def _as_int(value) -> int:
    """Coerce a usage count defensively; anything non-numeric counts as 0."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def parse_result_envelope(raw: str) -> Optional[UsageEnvelope]:
    """Parse `claude -p --output-format json` stdout into a UsageEnvelope.

    Returns None (caller falls back to plain text) when the input is not a JSON
    object, or has no string `result` field — a garbled/truncated envelope must
    degrade, never crash, and never masquerade as measured data.
    """
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    text = data.get("result")
    if not isinstance(text, str):
        return None
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    cost = data.get("total_cost_usd")
    return UsageEnvelope(
        text=text,
        input_tokens=_as_int(usage.get("input_tokens")),
        output_tokens=_as_int(usage.get("output_tokens")),
        cache_read_tokens=_as_int(usage.get("cache_read_input_tokens")),
        cache_creation_tokens=_as_int(usage.get("cache_creation_input_tokens")),
        cost_usd=float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None,
    )
