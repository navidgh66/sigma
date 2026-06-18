"""`sigma doctor` — diagnose the install, optionally repair it.

Runs the pure `checks` engine, renders a report, and (unless `--check`) offers to
apply each fixable problem's fix. Every mutating fix is confirm-gated by default;
`--yes` applies them without prompting; `--check` is strictly read-only and is
the CI-friendly mode (exit 1 if anything failed). `--update` pulls sigma and
re-vendors skills before re-checking.

Check-running, confirmation, and the updater are injected so the whole flow is
testable without touching the host.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from cli import checks as checks_mod
from cli import render
from cli.checks import FAIL, OK, Check


def _default_updater() -> None:
    """Update path: pull sigma, re-vendor skills. Best-effort, never fatal."""
    import subprocess

    from cli.paths import sigma_home

    home = sigma_home()
    if (home / ".git").exists():
        subprocess.call(["git", "-C", str(home), "pull", "--ff-only"])


def run_doctor(
    check_only: bool = False,
    auto_yes: bool = False,
    update: bool = False,
    run_all: Optional[Callable] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    updater: Optional[Callable] = None,
    use_rich: bool = True,
) -> int:
    """Return an exit code: 0 if no unresolved failures, 1 otherwise."""
    run_all = run_all or checks_mod.run_all
    confirm = confirm or render.confirm
    updater = updater or _default_updater

    if update:
        updater()

    results: List[Check] = run_all()
    render.print_checks(results, use_rich=use_rich)

    if not check_only:
        results = _apply_fixes(results, auto_yes, confirm, use_rich)

    counts = render.summarize(results)
    return 1 if counts.get(FAIL, 0) > 0 else 0


def _apply_fixes(
    results: List[Check],
    auto_yes: bool,
    confirm: Callable[[str], bool],
    use_rich: bool,
) -> List[Check]:
    """Confirm + apply each fixable problem. Returns the post-fix check list."""
    changed = False
    for c in results:
        if c.status == OK or not c.fixable:
            continue
        description, fixer = c.fix
        if not auto_yes and not confirm(f"Fix: {description}?"):
            continue
        ok = bool(fixer())
        changed = changed or ok
        if not ok:
            print(f"  ✗ fix did not complete: {description}")

    # Re-run checks once after applying fixes so the exit code reflects reality.
    if changed:
        results = checks_mod.run_all()
        render.print_checks(results, use_rich=use_rich)
    return results
