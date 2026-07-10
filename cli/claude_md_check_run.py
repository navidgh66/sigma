"""`sigma claude-md check` — check CLAUDE.md / CLAUDE.local.md against best-
practice research (deterministic checks + one qualitative agent pass).

Wires the pure logic (`cli/claude_md_check.py`) to real subprocesses:

  - resolve real pytest test count (`pytest --collect-only -q`, best-effort);
  - run deterministic + qualitative checks on CLAUDE.md (required) and
    CLAUDE.local.md (optional — skipped silently when absent, it's a personal
    file that may not exist);
  - aggregate findings across both files, gate, write a report.

Injectable subprocess/agent so the flow is testable without a real pytest run
or a real agent.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli import claude_md_check as cmc
from cli.review import Finding
from cli.runner import AgentRunner, write_artifact

LOCAL_FILENAME = "CLAUDE.local.md"
REPO_FILENAME = "CLAUDE.md"


@dataclass
class CheckResult:
    ok: bool
    findings: List[Finding] = field(default_factory=list)
    gate: Optional[object] = None
    report: str = ""
    report_path: Optional[Path] = None
    files_checked: List[str] = field(default_factory=list)
    error: Optional[str] = None


def real_test_count(
    root: Path,
    runner: Callable = subprocess.run,
) -> Optional[int]:
    """Best-effort real pytest test count via `--collect-only -q`.

    Returns None on any failure (pytest not installed/runnable, unexpected
    output) — the caller's stale-count check then skips rather than guessing.
    """
    try:
        proc = runner(
            ["python3", "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True, cwd=str(root), timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = (getattr(proc, "stdout", "") or "")
    for line in reversed(out.strip().splitlines()):
        m = re.match(r"^(\d+)\s+tests?\s+collected\b", line.strip())
        if m:
            return int(m.group(1))
    return None


def _check_one_file(
    path: Path,
    filename: str,
    root: Path,
    real_count: Optional[int],
    agent: Optional[AgentRunner],
) -> List[Finding]:
    """Run deterministic + qualitative checks on one file's text."""
    text = path.read_text()
    findings = cmc.run_deterministic_checks(text, filename, root, real_count)

    agent = agent or AgentRunner()
    prompt = cmc.build_qualitative_prompt(text, filename)
    result = agent.run(prompt, cwd=root, role="claude-md-check")
    if result.ok:
        findings += cmc.parse_qualitative_findings(result.output, filename)
    return findings


def run_check(
    root: Path,
    make_agent: Optional[Callable[[], AgentRunner]] = None,
    test_count_fn: Optional[Callable[[Path], Optional[int]]] = None,
) -> CheckResult:
    """Check CLAUDE.md (required) and CLAUDE.local.md (optional) in `root`.

    Missing CLAUDE.md is an error (nothing to check); missing CLAUDE.local.md is
    silently skipped (it's optional/personal, never required to exist).
    """
    root = root.resolve()
    make_agent = make_agent or AgentRunner
    test_count_fn = test_count_fn or real_test_count

    repo_path = root / REPO_FILENAME
    if not repo_path.exists():
        return CheckResult(ok=False, error=f"no {REPO_FILENAME} at {root}")

    count = test_count_fn(root)
    all_findings: List[Finding] = []
    files_checked: List[str] = []

    all_findings += _check_one_file(repo_path, REPO_FILENAME, root, count, make_agent())
    files_checked.append(REPO_FILENAME)

    local_path = root / LOCAL_FILENAME
    if local_path.exists():
        all_findings += _check_one_file(local_path, LOCAL_FILENAME, root, count, make_agent())
        files_checked.append(LOCAL_FILENAME)

    decision = cmc.gate(all_findings)
    report = cmc.render_report(all_findings, decision, " + ".join(files_checked))
    return CheckResult(
        ok=True, findings=all_findings, gate=decision, report=report,
        files_checked=files_checked,
    )


def write_report(root: Path, report: str) -> Path:
    """Write the check report under sigma/ (derived, git-ignored like other reports)."""
    out = root / "sigma" / "claude-md-check.md"
    return write_artifact(out, report + "\n")
