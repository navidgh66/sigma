"""`sigma uninstall` — reverse what the installer created (core surfaces only).

The installer (`installer/setup.sh`) creates four things:
  - the launcher  ~/.local/bin/sigma
  - the clone     ~/.sigma/            (which also holds ~/.sigma/.env — API keys)
  - the Claude Code plugin  (sigma@sigma)
  - the Claude Code marketplace  (sigma)

Uninstall removes exactly those. It deliberately LEAVES shared global state —
RTK, caveman, ccstatusline, the SessionStart hook — because those live in the
user's global ~/.claude/settings.json and may be wanted independently of sigma
(reverse them by hand if desired).

Pure planning (`build_plan`) is separated from execution (`run_uninstall`) so the
flow is fully testable without deleting anything. Every step is confirm-gated; the
secret-bearing ~/.sigma/.env is called out and confirmed SEPARATELY so API keys
are never dropped silently. `which`/`spawn`/`rmtree`/`unlink` are injectable.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


def _default_launcher() -> Path:
    return Path.home() / ".local" / "bin" / "sigma"


def _default_install_dir() -> Path:
    import os

    env = os.environ.get("SIGMA_HOME")
    return Path(env).expanduser() if env else Path.home() / ".sigma"


@dataclass
class UninstallPlan:
    """What an uninstall would touch — pure, derived from the filesystem."""

    launcher: Path
    install_dir: Path
    launcher_exists: bool
    install_dir_exists: bool
    has_secrets: bool  # ~/.sigma/.env present (API keys)
    has_claude_cli: bool  # plugin/marketplace removal possible

    def nothing_to_do(self) -> bool:
        return not (
            self.launcher_exists or self.install_dir_exists or self.has_claude_cli
        )


def build_plan(
    launcher: Optional[Path] = None,
    install_dir: Optional[Path] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
) -> UninstallPlan:
    """Inspect the filesystem and report what an uninstall would remove. Pure."""
    which = which or shutil.which
    launcher = launcher or _default_launcher()
    install_dir = install_dir or _default_install_dir()
    return UninstallPlan(
        launcher=launcher,
        install_dir=install_dir,
        launcher_exists=launcher.is_file() or launcher.is_symlink(),
        install_dir_exists=install_dir.is_dir(),
        has_secrets=(install_dir / ".env").is_file(),
        has_claude_cli=which("claude") is not None,
    )


@dataclass
class UninstallResult:
    removed: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def run_uninstall(
    plan: UninstallPlan,
    confirm: Callable[[str], bool],
    spawn: Optional[Callable[[List[str]], int]] = None,
    rmtree: Optional[Callable[[Path], None]] = None,
    unlink: Optional[Callable[[Path], None]] = None,
    assume_yes: bool = False,
) -> UninstallResult:
    """Execute the plan, confirming each surface. Returns what changed.

    The install dir is the only secret-bearing surface; when ~/.sigma/.env is
    present its deletion is called out in the confirm prompt and (unless
    `assume_yes`) requires its own explicit yes. All removals are best-effort:
    a failure is recorded in `errors`, never raised, so one stuck surface never
    blocks the others.
    """
    import subprocess

    spawn = spawn or subprocess.call
    rmtree = rmtree or (lambda p: shutil.rmtree(p, ignore_errors=False))
    unlink = unlink or (lambda p: p.unlink())
    res = UninstallResult()

    def _ask(msg: str) -> bool:
        return True if assume_yes else confirm(msg)

    # 1. Launcher (~/.local/bin/sigma).
    if plan.launcher_exists:
        if _ask(f"Remove the sigma launcher at {plan.launcher}?"):
            try:
                unlink(plan.launcher)
                res.removed.append(str(plan.launcher))
            except OSError as exc:
                res.errors.append(f"launcher: {exc}")
        else:
            res.skipped.append(str(plan.launcher))

    # 2. Install dir (~/.sigma) — warn separately when it holds API keys.
    if plan.install_dir_exists:
        msg = f"Remove the sigma install dir {plan.install_dir}?"
        if plan.has_secrets:
            msg = (
                f"⚠ {plan.install_dir}/.env holds your API keys (GEMINI/OPENAI). "
                f"Remove the entire install dir {plan.install_dir} INCLUDING those keys?"
            )
        if _ask(msg):
            try:
                rmtree(plan.install_dir)
                res.removed.append(str(plan.install_dir))
            except OSError as exc:
                res.errors.append(f"install dir: {exc}")
        else:
            res.skipped.append(str(plan.install_dir))

    # 3. Claude Code plugin + marketplace (only if the CLI is present).
    if plan.has_claude_cli:
        if _ask("Remove the sigma Claude Code plugin + marketplace?"):
            ok_all = True
            for argv in (
                ["claude", "plugin", "uninstall", "sigma@sigma"],
                ["claude", "plugin", "marketplace", "remove", "sigma"],
            ):
                try:
                    if spawn(argv) != 0:
                        ok_all = False
                except OSError as exc:
                    res.errors.append(f"plugin ({argv[2]}): {exc}")
                    ok_all = False
            res.removed.append("claude plugin sigma@sigma + marketplace") if ok_all else \
                res.errors.append("plugin/marketplace removal returned non-zero")
        else:
            res.skipped.append("claude plugin + marketplace")

    return res
