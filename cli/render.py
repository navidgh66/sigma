"""Presentation helpers for doctor/onboard: the σ logo, check output, prompts.

Uses rich when available for color/boxes, falls back to plain print otherwise so
the commands work on a minimal terminal. Pure-ish: only prints and reads input;
all decision logic lives in the callers.
"""

from __future__ import annotations

from typing import Dict, List

from cli.checks import FAIL, OK, WARN, Check

_LOGO = r"""
  ███████╗██╗ ██████╗ ███╗   ███╗ █████╗
  ██╔════╝██║██╔════╝ ████╗ ████║██╔══██╗
  ███████╗██║██║  ███╗██╔████╔██║███████║
  ╚════██║██║██║   ██║██║╚██╔╝██║██╔══██║
  ███████║██║╚██████╔╝██║ ╚═╝ ██║██║  ██║
  ╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝
  σ · personal AI workflow toolkit
  created by Navid Ghayazi · github.com/navidgh66/sigma
"""

_GLYPH = {OK: "✓", WARN: "⚠", FAIL: "✗"}
_STYLE = {OK: "green", WARN: "yellow", FAIL: "red"}


def logo() -> str:
    return _LOGO


def _rich_console():
    try:
        from rich.console import Console

        return Console()
    except ImportError:
        return None


def print_logo(use_rich: bool = True) -> None:
    console = _rich_console() if use_rich else None
    if console is not None:
        console.print(f"[bold cyan]{_LOGO}[/]")
    else:
        print(_LOGO)


def print_update_banner(use_rich: bool = True) -> None:
    """Show the σ logo + an update header before refreshing CLI + plugin."""
    print_logo(use_rich=use_rich)
    line = "↻ Updating sigma — CLI (git pull) + plugin (claude plugin update)"
    console = _rich_console() if use_rich else None
    if console is not None:
        console.print(f"[bold cyan]{line}[/]")
    else:
        print(line)


def print_checks(checks: List[Check], use_rich: bool = True) -> None:
    console = _rich_console() if use_rich else None
    if console is not None:
        from rich.table import Table

        table = Table(show_header=True, header_style="bold")
        table.add_column("")
        table.add_column("check")
        table.add_column("detail")
        for c in checks:
            glyph = f"[{_STYLE[c.status]}]{_GLYPH[c.status]}[/]"
            table.add_row(glyph, c.name, c.detail)
        console.print(table)
    else:
        for c in checks:
            print(f"  {_GLYPH[c.status]} {c.name}: {c.detail}")


def summarize(checks: List[Check]) -> Dict[str, int]:
    counts = {OK: 0, WARN: 0, FAIL: 0}
    for c in checks:
        counts[c.status] = counts.get(c.status, 0) + 1
    return counts


def confirm(prompt: str, default: bool = False) -> bool:
    """Ask a yes/no question. Empty input takes `default` (no, by default)."""
    suffix = " [y/N] " if not default else " [Y/n] "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not answer:
        return default
    return answer in ("y", "yes")
