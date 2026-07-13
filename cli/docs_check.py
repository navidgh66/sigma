"""Pure cross-surface docs-consistency checks — kill the drift class.

sigma's release checklist ("a version bump MUST land with a README/CLAUDE.md
update") is human-enforced and has demonstrably lost: on 2026-07-13 the repo
simultaneously claimed 232 (PLAYGROUND.md), 779 (README badge) and 866
(CLAUDE.md) tests against a real collected count of ~900. These checks make
that class of drift mechanical:

  - version parity: `cli/__init__.py.__version__` == `.claude-plugin/plugin.json`;
  - test-count claims: every "N tests"/"N passed"/badge number in the doc
    surfaces must match the real collected count.

Same shape as `cli/claude_md_check.py` (whose gate/report renderers are
reused): pure functions over text → `review.Finding`s, no I/O, no subprocess.
`real_count=None` (caller couldn't collect) skips count checks entirely —
never flag on absent evidence (the prune law).
"""

from __future__ import annotations

import re
from typing import List, Optional

from cli.review import Finding

AXIS = "docs-check"

_INIT_VERSION_RE = re.compile(r"__version__\s*=\s*[\"']([^\"']+)[\"']")
_PLUGIN_VERSION_RE = re.compile(r"\"version\"\s*:\s*\"([^\"]+)\"")

# Doc claims that carry a test count. Three-digit floor on the bare patterns so
# incidental small numbers ("22 passed" in a subset-run example) don't flag;
# the explicit "pytest tests" phrasing flags at any width.
_COUNT_PATTERNS = (
    re.compile(r"\btests-(\d+)%20passing\b"),               # README badge
    re.compile(r"\b(\d+)\s+pytest\s+tests\b", re.IGNORECASE),
    re.compile(r"\b(\d{3,6})\s+tests\b"),
    re.compile(r"\b(\d{3,6})\s+passed\b"),
)


def check_version_parity(init_text: str, plugin_text: str) -> List[Finding]:
    """The CLI and the plugin manifest must carry the SAME version string."""
    init_m = _INIT_VERSION_RE.search(init_text or "")
    plugin_m = _PLUGIN_VERSION_RE.search(plugin_text or "")
    if not init_m or not plugin_m:
        missing = "cli/__init__.py" if not init_m else ".claude-plugin/plugin.json"
        return [Finding(
            axis=AXIS, severity="HIGH", file=missing, line=None,
            message="could not parse a version string — parity unverifiable",
        )]
    if init_m.group(1) != plugin_m.group(1):
        return [Finding(
            axis=AXIS, severity="HIGH", file=".claude-plugin/plugin.json", line=None,
            message=f"version mismatch: cli/__init__.py says {init_m.group(1)}, "
                    f"plugin.json says {plugin_m.group(1)} — the release checklist "
                    "requires both to bump together",
        )]
    return []


def check_test_count_claims(text: str, filename: str, real_count: Optional[int]) -> List[Finding]:
    """Flag every numeric test-count claim that doesn't match the real count."""
    if real_count is None or not text:
        return []
    findings: List[Finding] = []
    seen_lines = set()
    for pattern in _COUNT_PATTERNS:
        for m in pattern.finditer(text):
            claimed = int(m.group(1))
            lineno = text.count("\n", 0, m.start()) + 1
            if claimed == real_count or lineno in seen_lines:
                continue
            seen_lines.add(lineno)
            findings.append(Finding(
                axis=AXIS, severity="HIGH", file=filename, line=lineno,
                message=f"claims {claimed} tests but the real collected count is "
                        f"{real_count} — stale counts are the drift signal the "
                        "release checklist exists to prevent",
            ))
    return findings
