"""Pure logic for checking CLAUDE.md / CLAUDE.local.md against best-practice
research (sigma:2026-07-10 deep-research pass — official Anthropic guidance +
community consensus + real-world examples).

Two layers, mirroring `cli/review.py`'s deterministic-then-agent shape:

  - Deterministic checks (`check_*`, no agent, instant): line-count thresholds,
    pasted-code-block detection, broken `@path` imports, stale test-count claims,
    placeholder markers. All return `review.Finding`s so the report format and
    the CRITICAL/HIGH gate are shared with `/review` — one finding vocabulary
    across sigma.
  - A qualitative agent pass (`build_qualitative_prompt` / `parse_qualitative_findings`):
    grades structure/specificity/redundancy against the research rubric using
    the SAME `FINDING | SEV | file:line | message` grammar review's axes emit.

The core rule this whole module encodes: "would removing this line cause Claude
to make a mistake? If not, it doesn't belong." Every check here is a proxy for
that rule, not a style nitpick.

Pure and deterministic where possible: no subprocess. Import-resolution and
test-count comparison need filesystem/count inputs, which the caller (thin
`cli/claude_md_check_run.py`) supplies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from cli.review import Finding, Gate

AXIS = "claude-md"

# Length thresholds, from the research: official docs say "target under 200
# lines"; community consensus converges on the same number with a ~300-line
# outer ceiling before adherence measurably degrades.
_LENGTH_WARN = 200
_LENGTH_FAIL = 300

# A pasted code block longer than this is a "snippet that will go stale" smell —
# the research's near-universal "use file:line pointers, not pasted code" rule.
_CODE_BLOCK_WARN_LINES = 15

_FENCE_RE = re.compile(r"^```")
_IMPORT_RE = re.compile(r"@([./~][\w./-]*|\w[\w./-]*\.\w+)")
_TEST_COUNT_RE = re.compile(r"\b(\d+)\s+pytest\s+tests\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME)\b")


def check_length(text: str, filename: str) -> List[Finding]:
    """Flag a file that's grown past the research's length thresholds."""
    n = len(text.splitlines())
    if n > _LENGTH_FAIL:
        return [Finding(
            axis=AXIS, severity="HIGH", file=filename, line=None,
            message=f"{n} lines — over the ~{_LENGTH_FAIL}-line ceiling where "
                    "adherence measurably degrades (research: bloat causes Claude "
                    "to silently ignore parts of the file, not fail loudly). Prune.",
        )]
    if n > _LENGTH_WARN:
        return [Finding(
            axis=AXIS, severity="MEDIUM", file=filename, line=None,
            message=f"{n} lines — over the official ~{_LENGTH_WARN}-line target. "
                    "For each line, ask: would removing this cause a mistake?",
        )]
    return []


def check_pasted_code_blocks(text: str, filename: str) -> List[Finding]:
    """Flag a fenced code block longer than the threshold (use file:line instead).

    Unclosed fences are ignored (nothing to reliably measure) rather than raising.
    """
    findings: List[Finding] = []
    lines = text.splitlines()
    fence_start: Optional[int] = None
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line.strip()):
            if fence_start is None:
                fence_start = i
            else:
                block_len = i - fence_start - 1
                if block_len > _CODE_BLOCK_WARN_LINES:
                    findings.append(Finding(
                        axis=AXIS, severity="MEDIUM", file=filename, line=fence_start + 1,
                        message=f"pasted code block is {block_len} lines — use a "
                                "file:line pointer instead, a snippet this long will "
                                "go stale",
                    ))
                fence_start = None
    return findings


def check_imports(text: str, file_path: Path) -> List[Finding]:
    """Flag a `@path/to/file` import that doesn't resolve on disk.

    Matches Claude Code's own import syntax: skips code spans/fences (backtick-
    wrapped or fenced) since those are literal citations, not real imports.
    Relative paths resolve relative to the importing file, per official docs.
    """
    findings: List[Finding] = []
    lines = text.splitlines()
    in_fence = False
    for lineno, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in _IMPORT_RE.finditer(line):
            # Skip an @import that sits inside a backtick-wrapped span on this line.
            if _inside_backticks(line, m.start()):
                continue
            ref = m.group(1)
            resolved = _resolve_import(ref, file_path)
            if not resolved.exists():
                findings.append(Finding(
                    axis=AXIS, severity="HIGH", file=str(file_path.name), line=lineno,
                    message=f"@{ref} does not resolve to a real file — broken import",
                ))
    return findings


def _inside_backticks(line: str, pos: int) -> bool:
    """True if `pos` in `line` falls between an odd/even pair of backticks."""
    before = line[:pos]
    return before.count("`") % 2 == 1


def _resolve_import(ref: str, file_path: Path) -> Path:
    """Resolve an `@ref` per official docs: relative to the IMPORTING FILE, not cwd."""
    if ref.startswith("~"):
        return Path(ref).expanduser()
    if ref.startswith("/"):
        return Path(ref)
    return (file_path.parent / ref).resolve()


def check_test_count_claims(text: str, filename: str, real_count: Optional[int]) -> List[Finding]:
    """Flag a "N pytest tests" claim that doesn't match the real, current count.

    `real_count=None` (caller couldn't determine it, e.g. pytest not runnable)
    skips the check entirely rather than guessing — never flag on absent evidence.
    """
    if real_count is None:
        return []
    findings: List[Finding] = []
    for m in _TEST_COUNT_RE.finditer(text):
        claimed = int(m.group(1))
        if claimed != real_count:
            lineno = text.count("\n", 0, m.start()) + 1
            findings.append(Finding(
                axis=AXIS, severity="MEDIUM", file=filename, line=lineno,
                message=f"claims {claimed} pytest tests, but the real count is "
                        f"{real_count} — a stale count actively misleads an agent",
            ))
    return findings


def check_placeholders(text: str, filename: str) -> List[Finding]:
    """Flag TODO/TBD/FIXME markers — the "no placeholders" rule."""
    findings: List[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _PLACEHOLDER_RE.finditer(line):
            findings.append(Finding(
                axis=AXIS, severity="LOW", file=filename, line=lineno,
                message=f"placeholder marker '{m.group(1)}' — resolve or remove",
            ))
    return findings


def run_deterministic_checks(
    text: str,
    filename: str,
    project_root: Path,
    real_test_count: Optional[int],
) -> List[Finding]:
    """Run every deterministic check and return the combined findings."""
    file_path = project_root / filename
    findings: List[Finding] = []
    findings += check_length(text, filename)
    findings += check_pasted_code_blocks(text, filename)
    findings += check_imports(text, file_path)
    findings += check_test_count_claims(text, filename, real_test_count)
    findings += check_placeholders(text, filename)
    return findings


# --------------------------------------------------------------------------- #
# Qualitative (agent) pass — reuses review's FINDING grammar
# --------------------------------------------------------------------------- #
_RUBRIC = """You are grading a CLAUDE.md-style file against sigma's CLAUDE.md
best-practice research (official Anthropic guidance + community consensus +
real-world examples from cloudflare/workers-sdk, vercel/ai, supabase, humanlayer,
langchain). Grade against these criteria, most important first:

1. Specificity test: for each instruction, would removing it cause a mistake? Flag
   vague/self-evident instructions ("write clean code", "keep files organized").
2. Include/exclude discipline: flag anything a linter would already enforce,
   anything discoverable by reading the code, detailed API docs that should be a
   link instead, or long tutorials/explanations.
3. Imperative voice: flag hedged language ("we generally prefer X") instead of
   direct commands ("use X").
4. Redundancy/contradiction: flag instructions that repeat each other or conflict.
5. WHAT/WHY/HOW coverage: does the file give Claude what it needs to know (tech
   stack/structure), why (purpose), and how (workflow/verification steps) —
   without over-explaining any one of the three?
6. Register: flag content written for human onboarding (README voice) rather
   than agent instructions (e.g. narrative history, marketing framing).

Report each real, non-trivial issue as exactly one line:
FINDING | SEVERITY | {filename}:LINE | message

Where SEVERITY is one of CRITICAL, HIGH, MEDIUM, LOW. Use HIGH only for something
that would genuinely mislead or actively harm every session (e.g. a directly
contradictory instruction); most structural/specificity issues are MEDIUM or LOW.
If the file is already good, emit no FINDING lines at all — do not invent issues
to seem thorough."""


def build_qualitative_prompt(text: str, filename: str) -> str:
    """Build the agent prompt that grades `text` against the research rubric."""
    rubric = _RUBRIC.format(filename=filename)
    return (
        f"{rubric}\n\n"
        f"--- {filename} ---\n{text}\n--- end {filename} ---\n"
    )


def parse_qualitative_findings(output: str, filename: str) -> List[Finding]:
    """Parse the agent's `FINDING | SEV | file:line | message` lines.

    Reuses `review.parse_findings` — the same grammar, so a qualitative
    claude-md finding and a review finding never need two parsers.
    """
    from cli.review import parse_findings

    return parse_findings(AXIS, output)


# --------------------------------------------------------------------------- #
# Gate + report
# --------------------------------------------------------------------------- #
def gate(findings: List[Finding]) -> Gate:
    """FAIL on any CRITICAL/HIGH finding, same law as `/review`'s axis gate.

    No "inconclusive axis" concept here (there's exactly one axis, always run
    deterministically) — an empty finding list is a clean PASS, not skepticism
    about whether the check ran (unlike review's multi-axis inconclusive case).
    """
    blocking = [f for f in findings if f.is_blocking]
    passed = not blocking
    reason = "no CRITICAL/HIGH findings" if passed else f"{len(blocking)} blocking finding(s)"
    return Gate(passed=passed, blocking=blocking, inconclusive_axes=[], reason=reason)


def render_report(findings: List[Finding], decision: Gate, filename: str) -> str:
    """Render the markdown report, reusing review's finding render() format."""
    mark = "✅ PASS" if decision.passed else "❌ FAIL"
    lines = [f"# claude-md check: {filename}", "", f"**{mark}** — {decision.reason}", ""]
    if not findings:
        lines.append("No findings.")
    else:
        lines.append("## Findings")
        lines.append("")
        for f in findings:
            lines.append(f.render())
    return "\n".join(lines)
