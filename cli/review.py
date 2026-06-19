"""Pure logic for sigma's three-axis review of team-authored changes.

`/review` (in-session) and `sigma review` (CLI, parallel + CI gate) both review a
**change set** — a local `git diff` or a PR diff — through three distinct agents:

  1. code        — bugs, security, quality, conventions
  2. ml-logic     — ML reasoning vs the logic profile (splits, leakage, metrics,
                    reward, eval-determinism); reuses per-domain logic-evaluator.md
  3. system-logic — control flow, data contracts, concurrency, state, API boundaries

This module owns everything testable without a real agent: parsing the diff into a
change set, inferring which domains a change touches, building each axis prompt
(injecting profile + recalled lessons + staleness banner), parsing findings out of
an agent reply, aggregating/deduping them, and the gate decision (FAIL on any
CRITICAL/HIGH). The subprocess wiring lives in `cli/review_run.py`.

Conventions preserved from the loop:
  - the three axis runners MUST be distinct instances (maker≠checker analog) —
    `ensure_distinct_axes` raises ValueError otherwise;
  - findings are parsed skeptically — an axis that produced no parsable verdict is
    treated as inconclusive, never as a silent pass;
  - empty diff / missing profile never hard-fail (fail-safe degradation).

Pure and deterministic: no subprocess, no timestamp generated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from cli.paths import DOMAINS

# The three review axes. Each maps to a distinct agent + a lens. The ml-logic axis
# is grounded in the per-domain logic-evaluator.md; the others use the prompt body.
AXES = ("code", "ml-logic", "system-logic")

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
# A finding at or above this severity fails the gate (Q5 verdict=3).
BLOCKING_SEVERITIES = frozenset({"CRITICAL", "HIGH"})

# When no path hint matches, the ml-logic axis must still grade GENERIC ML
# invariants (leakage, splits, metrics, validation) — so the default is the
# classic-ml logic-evaluator, NOT ai-agent-engineering (whose evaluator grades
# agent control-flow and would be structurally silent on ML correctness).
DEFAULT_DOMAIN = "classic-ml"

# Map a path fragment → domain, so a change can be routed to the right ml-logic
# criteria without a config. First match wins; falls back to DEFAULT_DOMAIN.
_DOMAIN_HINTS = (
    ("nlp", "nlp"),
    ("token", "nlp"),
    ("rl", "rl"),
    ("reward", "rl"),
    ("agent", "ai-agent-engineering"),
    ("llm", "llm-engineering"),
    ("prompt", "llm-engineering"),
    ("mlops", "mlops"),
    ("deploy", "mlops"),
    ("serve", "mlops"),
    ("etl", "data-engineering"),
    ("pipeline", "data-engineering"),
    ("ingest", "data-engineering"),
    ("analysis", "data-analysis"),
    ("notebook", "data-analysis"),
    ("deep", "deep-learning"),
    ("torch", "deep-learning"),
    ("net", "deep-learning"),
)


# --------------------------------------------------------------------------- #
# Change set
# --------------------------------------------------------------------------- #
@dataclass
class ChangeSet:
    """A resolved set of changes to review: touched files + the raw diff text."""

    files: List[str]
    diff: str
    source: str = "local"  # "local" or "pr"
    ref: Optional[str] = None  # branch range or PR number/URL

    @property
    def is_empty(self) -> bool:
        return not self.diff.strip() or not self.files


# Match `diff --git a/<path> b/<path>` and `+++ b/<path>` lines to extract files.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")
_PLUSPLUS_RE = re.compile(r"^\+\+\+ b/(?P<path>.+)$")


def parse_changed_files(diff: str) -> List[str]:
    """Extract the changed file paths from a unified diff (deterministic order).

    Handles both the `diff --git` header and `+++ b/` lines; ignores /dev/null
    (deletions still report the `a/` path via the git header). Deduped, preserving
    first-seen order so output is stable.
    """
    seen: Dict[str, None] = {}
    for line in diff.splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            path = m.group("b")
            if path == "/dev/null":
                path = m.group("a")
            seen.setdefault(path, None)
            continue
        m = _PLUSPLUS_RE.match(line)
        if m and m.group("path") != "/dev/null":
            seen.setdefault(m.group("path"), None)
    return list(seen.keys())


def build_change_set(diff: str, source: str = "local", ref: Optional[str] = None) -> ChangeSet:
    """Build a ChangeSet from raw diff text (files parsed out of the diff)."""
    return ChangeSet(files=parse_changed_files(diff), diff=diff, source=source, ref=ref)


def infer_domains(files: Sequence[str]) -> List[str]:
    """Infer which sigma domains a change touches, from its file paths.

    Path-fragment heuristic (no config needed). Returns a deterministic, deduped
    list; always non-empty (falls back to DEFAULT_DOMAIN). The ml-logic axis loads
    these domains' logic-evaluator.md files.
    """
    found: Dict[str, None] = {}
    for f in files:
        low = f.lower()
        for hint, domain in _DOMAIN_HINTS:
            if hint in low and domain in DOMAINS:
                found.setdefault(domain, None)
    if not found:
        return [DEFAULT_DOMAIN]
    return list(found.keys())


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    """One review finding from one axis."""

    axis: str
    severity: str
    file: str
    line: Optional[int]
    message: str

    @property
    def is_blocking(self) -> bool:
        return self.severity.upper() in BLOCKING_SEVERITIES

    def key(self) -> tuple:
        """Dedup key: same file+line+message is the same finding (axis-agnostic)."""
        return (self.file, self.line, self.message.strip().lower())

    def render(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else (self.file or "-")
        return f"- **{self.severity.upper()}** [{self.axis}] {loc} — {self.message.strip()}"


# Findings are emitted by agents as one line each, in a strict, easy-to-parse form:
#   FINDING | <SEVERITY> | <file>:<line> | <message>
# (line optional: `<file>` or `-` are allowed). Anything else is ignored, so prose
# around the findings never corrupts the parse.
_FINDING_RE = re.compile(
    r"^\s*FINDING\s*\|\s*(?P<sev>[A-Za-z]+)\s*\|\s*(?P<loc>[^|]*)\s*\|\s*(?P<msg>.+?)\s*$"
)
_LOC_RE = re.compile(r"^(?P<file>.+?)(?::(?P<line>\d+))?$")


def parse_findings(axis: str, output: str) -> List[Finding]:
    """Parse `FINDING | SEV | file:line | message` lines from one axis's output.

    Unknown severities are coerced to MEDIUM (never silently dropped — an unknown
    severity must not become a non-blocking no-op by accident). Lines that do not
    match the FINDING grammar are ignored.
    """
    findings: List[Finding] = []
    for line in output.splitlines():
        m = _FINDING_RE.match(line)
        if not m:
            continue
        sev = m.group("sev").upper()
        if sev not in SEVERITIES:
            sev = "MEDIUM"
        loc = (m.group("loc") or "").strip()
        file, lineno = _split_loc(loc)
        findings.append(
            Finding(axis=axis, severity=sev, file=file, line=lineno, message=m.group("msg"))
        )
    return findings


def _split_loc(loc: str) -> tuple:
    """Split a `file:line` location into (file, line|None). `-`/empty → ('', None)."""
    if not loc or loc == "-":
        return "", None
    m = _LOC_RE.match(loc)
    if not m:
        return loc, None
    line = m.group("line")
    return m.group("file"), (int(line) if line else None)


@dataclass
class AxisResult:
    """The outcome of running one review axis."""

    axis: str
    ran: bool
    findings: List[Finding] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def inconclusive(self) -> bool:
        """An axis that did not run cleanly is inconclusive (not a pass)."""
        return not self.ran


def aggregate(results: Sequence[AxisResult]) -> List[Finding]:
    """Merge findings across axes, deduped by (file, line, message).

    Deterministic: severity-then-axis ordered so the most serious findings lead a
    report. First occurrence of a dedup key wins (axes are processed in AXES order
    upstream, keeping it stable).
    """
    by_key: Dict[tuple, Finding] = {}
    for res in results:
        for f in res.findings:
            by_key.setdefault(f.key(), f)
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(
        by_key.values(),
        key=lambda f: (order.get(f.severity.upper(), len(SEVERITIES)), f.axis, f.file, f.line or 0),
    )


@dataclass
class Gate:
    """The overall review verdict."""

    passed: bool
    blocking: List[Finding] = field(default_factory=list)
    inconclusive_axes: List[str] = field(default_factory=list)
    reason: str = ""


def gate(results: Sequence[AxisResult]) -> Gate:
    """Decide PASS/FAIL: fail on any CRITICAL/HIGH finding OR an inconclusive axis.

    Skeptical, mirroring `loop._verdict_pass`: an axis that did not run is NOT a
    pass — its silence cannot be read as approval. The blocking-severity gate is
    Q5 verdict=3 (findings always reported; gate trips only on CRITICAL/HIGH).
    """
    findings = aggregate(results)
    blocking = [f for f in findings if f.is_blocking]
    inconclusive = [r.axis for r in results if r.inconclusive]
    passed = not blocking and not inconclusive
    if passed:
        reason = "no blocking findings; all axes conclusive"
    elif blocking and inconclusive:
        reason = (
            f"{len(blocking)} blocking finding(s) and inconclusive axes: "
            + ", ".join(inconclusive)
        )
    elif blocking:
        reason = f"{len(blocking)} blocking (CRITICAL/HIGH) finding(s)"
    else:
        reason = "inconclusive axes (no clean verdict): " + ", ".join(inconclusive)
    return Gate(passed=passed, blocking=blocking, inconclusive_axes=inconclusive, reason=reason)


# --------------------------------------------------------------------------- #
# Prompt building
# --------------------------------------------------------------------------- #
_FINDING_FORMAT = (
    "Report EACH issue on its own line, EXACTLY:\n"
    "FINDING | <CRITICAL|HIGH|MEDIUM|LOW> | <file>:<line> | <one-line message>\n"
    "Use `-` for the location if a finding is not tied to a specific line. After "
    "the findings, end with a single line exactly `VERDICT: PASS` (no blocking "
    "issues) or `VERDICT: FAIL`."
)

_AXIS_BRIEF = {
    "code": (
        "You are the CODE reviewer (one of three distinct review agents; you do NOT "
        "grade ML reasoning or system architecture — other agents own those). Review "
        "the change set for bugs, security flaws, error handling, and convention "
        "violations. Be concrete: cite file:line."
    ),
    "ml-logic": (
        "You are the ML-LOGIC reviewer (distinct from the code and system-logic "
        "agents). Apply the domain logic-evaluator criteria below to the CHANGE, "
        "grounded in the logic profile's ML-logic invariants. Flag: broken "
        "data-split / leakage guards, silent metric or loss changes, reward-shaping "
        "errors, eval non-determinism, train/serve skew. A clean implementation of "
        "the WRONG ML logic is a finding."
    ),
    "system-logic": (
        "You are the SYSTEM-LOGIC reviewer (distinct from the code and ML-logic "
        "agents). Grounded in the logic profile's system-logic invariants, review "
        "the CHANGE for control-flow soundness (termination, dead ends), "
        "data-contract / schema breaks, concurrency and state coherence, "
        "API-boundary compatibility, and failure handling. Flag violations of a "
        "stated system invariant."
    ),
}


def build_axis_prompt(
    axis: str,
    change: ChangeSet,
    profile_text: str = "",
    recall_block: str = "",
    staleness_banner: str = "",
    logic_evaluator_text: str = "",
) -> str:
    """Build the prompt for one review axis.

    Injects (in order): staleness banner → recalled lessons → logic profile →
    (ml-logic only) the domain logic-evaluator criteria → the change set → the
    strict finding format. Any of the optional blocks may be empty (fail-safe:
    an empty profile/recall leaves a coherent, smaller prompt — never an error).
    """
    if axis not in AXES:
        raise ValueError(f"unknown axis: {axis!r} (expected one of {AXES})")

    parts: List[str] = [_AXIS_BRIEF[axis], ""]
    if staleness_banner:
        parts += [staleness_banner, ""]
    if recall_block:
        parts += [recall_block, ""]
    if profile_text.strip():
        parts += ["--- logic profile (system invariants) ---", profile_text.strip(),
                  "--- end logic profile ---", ""]
    if axis == "ml-logic" and logic_evaluator_text.strip():
        parts += ["--- domain logic-evaluator criteria ---", logic_evaluator_text.strip(),
                  "--- end criteria ---", ""]
    label = f"{change.source} change set" + (f" ({change.ref})" if change.ref else "")
    parts += [
        f"--- {label}: {len(change.files)} file(s) ---",
        ", ".join(change.files) if change.files else "(no files parsed)",
        "",
        "--- diff ---",
        change.diff.strip() or "(empty diff)",
        "--- end diff ---",
        "",
        _FINDING_FORMAT,
    ]
    return "\n".join(parts)


def ensure_distinct_axes(runners: Sequence[object]) -> None:
    """Guard: the three axis runners must be distinct instances (maker≠checker).

    Mirrors `loop.execute_cycle`'s separation enforcement — raises ValueError if any
    two axis runners are the same object, so self-review across axes is impossible.
    """
    seen: List[int] = []
    for r in runners:
        if id(r) in seen:
            raise ValueError("review axes must use distinct agent instances")
        seen.append(id(r))


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def render_report(change: ChangeSet, results: Sequence[AxisResult], decision: Gate,
                  domains: Sequence[str]) -> str:
    """Render the full markdown review report (the always-written artifact)."""
    findings = aggregate(results)
    verdict = "✅ PASS" if decision.passed else "❌ FAIL"
    lines: List[str] = [
        f"# Review: {change.source} change set" + (f" ({change.ref})" if change.ref else ""),
        "",
        f"**Verdict: {verdict}** — {decision.reason}",
        "",
        f"*Files: {len(change.files)} · Domains: {', '.join(domains) or '-'} · "
        f"Findings: {len(findings)} · Axes: {', '.join(AXES)}*",
        "",
        "## Axis coverage",
        "",
    ]
    for res in results:
        if res.ran:
            status = f"ran ({len(res.findings)} finding(s))"
        else:
            status = f"⚠ inconclusive ({res.error or 'no clean verdict'})"
        lines.append(f"- **{res.axis}**: {status}")
    lines.append("")

    if findings:
        lines += ["## Findings", ""]
        lines += [f.render() for f in findings]
        lines.append("")
    else:
        lines += ["## Findings", "", "_None reported._", ""]

    lines += ["## Next", ""]
    if decision.passed:
        lines.append("→ change set clears the gate.")
    else:
        lines.append("→ address CRITICAL/HIGH findings (ratcheted into `skills/`); "
                     "re-run `/review`. Inconclusive axes must be re-run, not assumed clean.")
    lines.append("")
    return "\n".join(lines)


def render_pr_comment(change: ChangeSet, decision: Gate) -> str:
    """Render the short PR summary comment (PR mode only)."""
    verdict = "✅ PASS" if decision.passed else "❌ FAIL"
    head = f"**sigma review: {verdict}** — {decision.reason}"
    if not decision.blocking:
        return head + "\n\n_No blocking findings._"
    body = "\n".join(f.render() for f in decision.blocking)
    return f"{head}\n\n**Blocking findings:**\n{body}"
