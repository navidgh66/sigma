#!/usr/bin/env python3
"""sigma — personal AI workflow toolkit CLI.

Wraps Claude Code with the sigma pipeline and a multi-model research phase.
See docs/2026-06-16-sigma-design.md.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

# Allow running both as `python cli/main.py` and `python -m cli.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli import __version__
from cli.config import SigmaConfig, config_path, load_config, write_config
from cli.loop import (
    append_loop_log,
    incomplete_tasks,
    parse_tasks,
    plan_cycle,
)
from cli.models import available_models
from cli.paths import DOMAINS, spec_workspace
from cli.pipeline import STAGE_NAMES, load_stage, render_invocation
from cli.research import research


def _print(msg: str) -> None:
    print(msg)


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace) -> int:
    path = config_path()
    if path.exists() and not args.force:
        _print(f"sigma.config.yml already exists at {path}. Use --force to overwrite.")
        return 1

    domains = list(DOMAINS)
    if args.domains:
        requested = [d.strip() for d in args.domains.split(",") if d.strip()]
        unknown = [d for d in requested if d not in DOMAINS]
        if unknown:
            _print(f"✗ unknown domain(s): {', '.join(unknown)}")
            _print(f"  valid: {', '.join(DOMAINS)}")
            return 1
        domains = requested

    cfg = SigmaConfig(name=args.name or Path.cwd().name, domains=domains)
    errors = cfg.validate()
    if errors:
        for e in errors:
            _print(f"✗ {e}")
        return 1
    written = write_config(cfg)
    _print(f"✓ wrote {written}")
    _print(f"  domains: {', '.join(cfg.domains)}")
    _print(f"  models:  {', '.join(cfg.models)}")
    return 0


# --------------------------------------------------------------------------- #
# research
# --------------------------------------------------------------------------- #
def cmd_research(args: argparse.Namespace) -> int:
    cfg = load_config()
    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else cfg.models
    )
    ws = spec_workspace(args.topic)
    _print(f"sigma research — topic={args.topic!r}")
    _print(f"  models requested: {', '.join(models)}")
    avail = available_models(models)
    _print(f"  models available: {', '.join(avail) or '(none)'}")
    out = research(args.topic, models, ws)
    _print(f"✓ wrote {out}")
    _print("→ next: /propose")
    return 0


# --------------------------------------------------------------------------- #
# generic pipeline stage (propose..verify)
# --------------------------------------------------------------------------- #
def cmd_stage(args: argparse.Namespace) -> int:
    stage = load_stage(args._name)
    if stage is None:
        _print(f"✗ unknown stage: {args._name}")
        return 1
    if not stage.exists:
        _print(f"✗ command template missing: {stage.template_path}")
        return 1
    ws = spec_workspace(args.topic) if args.topic else None
    if ws is None:
        _print("✗ provide --topic to locate the spec workspace")
        return 1
    invocation = render_invocation(stage, ws)
    if args.dry_run:
        _print(invocation)
        return 0
    return _run_claude(invocation)


# --------------------------------------------------------------------------- #
# loop
# --------------------------------------------------------------------------- #
def cmd_loop(args: argparse.Namespace) -> int:
    cfg = load_config()
    ws = spec_workspace(args.topic)
    tasks_file = ws / "tasks.md"
    if not tasks_file.exists():
        _print(f"✗ no tasks.md at {tasks_file}. Run /tasks first.")
        return 1
    tasks = parse_tasks(tasks_file.read_text())
    pending = incomplete_tasks(tasks)
    _print(f"sigma loop — {len(pending)} pending / {len(tasks)} total")
    _print(f"  max_cycles: {cfg.loop.max_cycles}  worktrees: {cfg.loop.worktrees}")
    if not pending:
        _print("✓ all tasks complete")
        return 0
    # Plan (dry by default — real agent execution is wired separately).
    shown = 0
    for t in pending:
        if shown >= cfg.loop.max_cycles:
            _print(f"  … {len(pending) - shown} more (capped at max_cycles)")
            break
        plan = plan_cycle(t)
        _print(f"  • {t.id or '-'} [{plan.implementer_domain}] {t.title}")
        _print(f"    worktree={plan.worktree_name} maker≠checker={plan.valid_maker_checker()}")
        shown += 1
    append_loop_log(ws, f"planned {min(len(pending), cfg.loop.max_cycles)} cycle(s)")
    return 0


# --------------------------------------------------------------------------- #
# launch (default: open Claude Code with sigma context)
# --------------------------------------------------------------------------- #
def cmd_launch(args: argparse.Namespace) -> int:
    cfg = load_config()
    _print("σ sigma")
    _print(f"  project: {cfg.name}")
    _print(f"  domains: {', '.join(cfg.domains)}")
    if not shutil.which("claude"):
        _print("✗ claude CLI not found. Install Claude Code.")
        return 1
    if args.no_launch:
        return 0
    return _run_claude(None)


def _run_claude(prompt: Optional[str]) -> int:
    argv = ["claude"]
    if prompt is not None:
        argv += ["-p", prompt]
    try:
        return subprocess.call(argv)
    except FileNotFoundError:
        _print("✗ claude CLI not found.")
        return 1


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sigma", description="Personal AI workflow toolkit.")
    p.add_argument("--version", action="version", version=f"sigma {__version__}")
    sub = p.add_subparsers(dest="command")

    pi = sub.add_parser("init", help="Scaffold sigma.config.yml")
    pi.add_argument("--name", help="project name")
    pi.add_argument("--domains", help="comma list (default: all)")
    pi.add_argument("--force", action="store_true", help="overwrite existing config")
    pi.set_defaults(func=cmd_init)

    pr = sub.add_parser("research", help="Multi-model research")
    pr.add_argument("topic")
    pr.add_argument("--models", help="comma list: claude,gemini,gpt")
    pr.set_defaults(func=cmd_research)

    for name in STAGE_NAMES:
        if name in ("research", "loop"):
            continue
        sp = sub.add_parser(name, help=f"Pipeline stage: {name}")
        sp.add_argument("--topic", required=True, help="topic/slug locating the workspace")
        sp.add_argument("--dry-run", action="store_true", help="print invocation, do not run claude")
        sp.set_defaults(func=cmd_stage, _name=name)

    pl = sub.add_parser("loop", help="Autonomous loop planner")
    pl.add_argument("--topic", required=True)
    pl.set_defaults(func=cmd_loop)

    plaunch = sub.add_parser("launch", help="Open Claude Code with sigma context")
    plaunch.add_argument("--no-launch", action="store_true", help="print context, do not launch")
    plaunch.set_defaults(func=cmd_launch)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # Default action: launch.
        return cmd_launch(argparse.Namespace(no_launch=True))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
