"""`sigma doctor` — diagnose the install, optionally repair it.

Runs the pure `checks` engine, renders a report, and (unless `--check`) offers to
apply each fixable problem's fix. Every mutating fix is confirm-gated by default;
`--yes` applies them without prompting; `--check` is strictly read-only and is
the CI-friendly mode (exit 1 if anything failed). `--update` refreshes BOTH
install surfaces — git-pulls the CLI repo AND updates the Claude Code plugin —
before re-checking.

Check-running, confirmation, and the updater are injected so the whole flow is
testable without touching the host.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from cli import checks as checks_mod
from cli import render
from cli.checks import FAIL, OK, Check


def _default_updater(
    spawn: Optional[Callable[[List[str]], int]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> None:
    """Update both surfaces. Best-effort, never fatal.

    Two independent installs ship sigma: the CLI (this cloned repo = sigma_home)
    and the Claude Code PLUGIN (a version-pinned copy under
    ~/.claude/plugins/cache/). A `git pull` here only refreshes the CLI — the
    plugin slash-commands (/grill, /spec …) live elsewhere and must be refreshed
    through the `claude` CLI. So we do both:

    1. CLI: `git pull --ff-only` on sigma_home.
    2. Plugin: refresh the `sigma` marketplace, then `claude plugin update
       sigma@sigma` (needs a Claude Code restart to apply). Skipped silently when
       the `claude` binary is absent.

    `spawn` / `which` are injectable so the flow is testable without touching the
    host (mirrors caveman/rtk).
    """
    import shutil
    import subprocess

    from cli.paths import sigma_home

    spawn = spawn or subprocess.call
    which = which or shutil.which

    home = sigma_home()
    if (home / ".git").exists():
        spawn(["git", "-C", str(home), "pull", "--ff-only"])

    # Plugin surface — only when the `claude` CLI is on PATH (mirror caveman/rtk).
    if which("claude"):
        spawn(["claude", "plugin", "marketplace", "update", "sigma"])
        spawn(["claude", "plugin", "update", "sigma@sigma"])
        print("  ↻ plugin updated — restart Claude Code to load the new version.")


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
