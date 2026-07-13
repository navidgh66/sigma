"""Thin runner for `sigma docs-check`: gather surfaces, run pure checks, report.

Composes `cli.docs_check` (pure cross-surface checks) with the machinery the
claude-md checker already proved out: `claude_md_check_run.real_test_count`
for the real collected count and `claude_md_check.gate`/`render_report` for
the verdict + report format. Missing doc surfaces are skipped silently
(README-less repos exist); the two version files are required — sigma itself
always has both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli import claude_md_check as cmc
from cli import docs_check
from cli.claude_md_check_run import real_test_count
from cli.review import Finding
from cli.runner import write_artifact

# Doc surfaces scanned for stale test-count claims (repo-relative).
COUNT_SURFACES = ("README.md", "CLAUDE.md", "docs/PLAYGROUND.md")
INIT_FILE = "cli/__init__.py"
PLUGIN_FILE = ".claude-plugin/plugin.json"


@dataclass
class DocsCheckResult:
    ok: bool
    findings: List[Finding] = field(default_factory=list)
    gate: Optional[cmc.Gate] = None
    report: str = ""
    files_checked: List[str] = field(default_factory=list)
    real_count: Optional[int] = None
    error: Optional[str] = None


def _read(root: Path, rel: str) -> Optional[str]:
    path = root / rel
    if not path.exists():
        return None
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def run_docs_check(
    root: Path,
    test_count_fn: Optional[Callable[[Path], Optional[int]]] = None,
) -> DocsCheckResult:
    """Run every cross-surface consistency check against `root`."""
    root = root.resolve()
    test_count_fn = test_count_fn or real_test_count

    init_text = _read(root, INIT_FILE)
    plugin_text = _read(root, PLUGIN_FILE)
    if init_text is None or plugin_text is None:
        missing = INIT_FILE if init_text is None else PLUGIN_FILE
        return DocsCheckResult(ok=False, error=f"no {missing} at {root} — not a sigma checkout?")

    findings: List[Finding] = []
    files_checked: List[str] = [INIT_FILE, PLUGIN_FILE]
    findings += docs_check.check_version_parity(init_text, plugin_text)

    count = test_count_fn(root)
    for rel in COUNT_SURFACES:
        text = _read(root, rel)
        if text is None:
            continue
        files_checked.append(rel)
        findings += docs_check.check_test_count_claims(text, rel, count)

    decision = cmc.gate(findings)
    report = cmc.render_report(findings, decision, " + ".join(files_checked))
    return DocsCheckResult(
        ok=True, findings=findings, gate=decision, report=report,
        files_checked=files_checked, real_count=count,
    )


def write_report(root: Path, report: str) -> Path:
    """Write the report under sigma/ (derived, git-ignored like other reports)."""
    out = root / "sigma" / "docs-check.md"
    return write_artifact(out, report + "\n")
