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
    run_loop,
)
from cli.models import available_models
from cli.paths import DOMAINS, sigma_home, spec_workspace
from cli.research import research


def _now_iso() -> str:
    """Current timestamp for event stamping (kept in one place)."""
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


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
    deep = getattr(args, "deep", False)
    web = getattr(args, "web", False) and not deep  # deep wins if both given
    tag = "  [deep]" if deep else ("  [web]" if web else "")
    _print(f"sigma research — topic={args.topic!r}{tag}")
    _print(f"  models requested: {', '.join(models)}")
    avail = available_models(models)
    _print(f"  models available: {', '.join(avail) or '(none)'}")
    if deep:
        _print("  mode: deep (web-grounded — this may take a few minutes)")
    elif web:
        _print("  mode: web (quick web-grounded pass)")
    out = research(args.topic, models, ws, deep=deep, web=web)
    _print(f"✓ wrote {out}")
    _print("→ next: /propose")
    return 0


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
    _print(f"  max_cycles: {cfg.loop.max_cycles}  (sequential cycles, one workspace)")
    if not pending:
        _print("✓ all tasks complete")
        return 0

    if not args.execute:
        # Plan-only (default, safe): show what the loop would do.
        shown = 0
        for t in pending:
            if shown >= cfg.loop.max_cycles:
                _print(f"  … {len(pending) - shown} more (capped at max_cycles)")
                break
            plan = plan_cycle(t)
            _print(f"  • {t.id or '-'} [{plan.implementer_domain}] {t.title}")
            _print(f"    cycle={plan.worktree_name} maker≠checker={plan.valid_maker_checker()}")
            shown += 1
        append_loop_log(ws, f"planned {min(len(pending), cfg.loop.max_cycles)} cycle(s)")
        _print("  (plan only — pass --execute to run maker→checker cycles)")
        return 0

    # Execute: real maker→checker cycles with distinct agents.
    from cli.keepawake import keep_awake
    from cli.runner import AgentRunner

    skills_dir = sigma_home() / "skills"
    if args.keep_awake:
        _print("  ☕ keep-awake on (caffeinate)")
    if args.tdd:
        _print("  🧪 TDD mode: a distinct agent writes a failing test before each implementer")
    if args.team:
        _print("  👥 team mode: independent tasks run in parallel")
    with keep_awake(enabled=args.keep_awake):
        outcomes = run_loop(
            tasks,
            ws,
            skills_dir,
            cfg.loop.max_cycles,
            make_implementer=lambda: AgentRunner(),
            make_verifier=lambda: AgentRunner(),
            make_logic_checker=(lambda: AgentRunner()) if args.logic else None,
            make_test_writer=(lambda: AgentRunner()) if args.tdd else None,
            team=args.team,
            gate=args.gate,
        )
    if not outcomes and args.gate:
        _print("  gate: nothing to do — skipped (0 tokens)")
        return 0
    passed = sum(1 for o in outcomes if o.verified)
    _print(f"✓ ran {len(outcomes)} cycle(s): {passed} passed, {len(outcomes) - passed} failed")
    for o in outcomes:
        mark = "✓" if o.verified else "✗"
        _print(f"  {mark} {o.task_title}")
        if o.test_written is not None:
            _print(f"    test-first: {'✓ written' if o.test_written else '✗ failed'}")
        if o.ratcheted_skill:
            _print(f"    ratcheted → {o.ratcheted_skill}")
        if o.contradiction:
            _print(f"    ⚠ contradiction flagged → {o.contradiction}")
    return 0


# --------------------------------------------------------------------------- #
# hermes (conductor: route plain language → run stage(s))
# --------------------------------------------------------------------------- #
def cmd_hermes(args: argparse.Namespace) -> int:
    from cli.hermes import run_hermes
    from cli.keepawake import keep_awake
    from cli.runner import AgentRunner

    ws = spec_workspace(args.topic)
    ws.mkdir(parents=True, exist_ok=True)
    mode = "auto" if args.auto else "single-step"
    _print(f"σ hermes — topic={args.topic!r} mode={mode}{' terse' if args.terse else ''}")
    if args.keep_awake:
        _print("  ☕ keep-awake on (caffeinate)")
    with keep_awake(enabled=args.keep_awake):
        result = run_hermes(
            args.message,
            ws,
            auto=args.auto,
            terse=args.terse,
            make_runner=lambda: AgentRunner(),
            now=_now_iso(),
            gate=args.gate,
        )
    for stage in result.stages_run:
        _print(f"  • ran {stage}")
    if result.gate:
        _print(f"→ stopped at gate: {result.gate}")
    if not result.ok:
        _print("✗ hermes stopped on failure")
        return 1
    _print(f"✓ hermes ran {len(result.stages_run)} stage(s)")
    return 0


# --------------------------------------------------------------------------- #
# board (kanban projection over tasks + events)
# --------------------------------------------------------------------------- #
def cmd_board(args: argparse.Namespace) -> int:
    from cli import board

    ws = spec_workspace(args.topic)
    if not ws.exists():
        _print(f"✗ no spec workspace at {ws}. Run a stage or hermes first.")
        return 1
    if args.watch:
        _print(f"σ board — watching {ws} (Ctrl-C to stop)")
        board.render_live(ws)
    else:
        board.render_static(ws)
    return 0


# --------------------------------------------------------------------------- #
# doctor (diagnose + repair the install)
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> int:
    from cli.doctor import run_doctor

    return run_doctor(
        check_only=args.check,
        auto_yes=args.yes,
        update=args.update,
    )


# --------------------------------------------------------------------------- #
# onboard (friendly first-run setup)
# --------------------------------------------------------------------------- #
def cmd_onboard(args: argparse.Namespace) -> int:
    from cli.onboard import run_onboard

    run_onboard(name=args.name)
    return 0


# --------------------------------------------------------------------------- #
# learn (learn the codebase → ARCHITECTURE.md + .tours/<slug>.tour)
# --------------------------------------------------------------------------- #
def cmd_learn(args: argparse.Namespace) -> int:
    from cli.learn import run_learn
    from cli.paths import project_root

    root = project_root()
    _print(f"sigma learn — codebase at {root}")
    if args.persona:
        _print(f"  persona: {args.persona}")
    res = run_learn(
        root,
        persona=args.persona,
        topic=args.topic,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        _print("--- invocation (dry run) ---")
        _print(res.prompt)
        return 0
    if not res.ok:
        _print(f"✗ learn failed: {res.error}")
        return 1
    if res.architecture_path:
        _print(f"✓ wrote {res.architecture_path}")
    if res.tour_path:
        _print(f"✓ wrote {res.tour_path}")
        if res.tour_problems:
            _print(f"  ⚠ {len(res.tour_problems)} tour anchor issue(s):")
            for p in res.tour_problems:
                _print(f"    - {p}")
        else:
            _print("  ✓ all tour anchors valid")
    return 0


# --------------------------------------------------------------------------- #
# weave (weave stage artifacts → chain.html + chain.json)
# --------------------------------------------------------------------------- #
def cmd_weave(args: argparse.Namespace) -> int:
    from cli.weave import run_weave

    ws = spec_workspace(args.topic)
    if not args.dry_run and not ws.exists():
        _print(f"✗ no spec workspace at {ws}. Run a stage first.")
        return 1
    _print(f"σ weave — topic={args.topic!r}")
    res = run_weave(ws, topic=args.topic, slug=ws.name, dry_run=args.dry_run)
    if args.dry_run:
        _print("--- invocation (dry run) ---")
        _print(res.prompt)
        return 0
    if res.manifest_path:
        _print(f"✓ wrote {res.manifest_path}")
    if not res.ok:
        _print(f"✗ weave failed: {res.error}")
        return 1
    if res.html_path:
        _print(f"✓ wrote {res.html_path}")
        if res.html_problems:
            _print(f"  ⚠ {len(res.html_problems)} HTML issue(s):")
            for p in res.html_problems:
                _print(f"    - {p}")
        else:
            _print("  ✓ chain.html valid")
    return 0


# --------------------------------------------------------------------------- #
# profile (walk codebase → logic-profile.md grounding for review)
# --------------------------------------------------------------------------- #
def cmd_profile(args: argparse.Namespace) -> int:
    from cli.paths import project_root
    from cli.profile_run import run_profile

    root = project_root()
    _print(f"σ profile — codebase at {root}")
    res = run_profile(root, project_name=root.name, dry_run=args.dry_run)
    if args.dry_run:
        _print("--- invocation (dry run) ---")
        _print(res.prompt)
        return 0
    if not res.ok:
        _print(f"✗ profile failed: {res.error}")
        return 1
    if res.profile_path:
        _print(f"✓ wrote {res.profile_path}")
    if res.problems:
        _print(f"  ⚠ {len(res.problems)} issue(s):")
        for p in res.problems:
            _print(f"    - {p}")
    else:
        _print("  ✓ both invariant sections present")
    return 0


# --------------------------------------------------------------------------- #
# review (three-axis review of a change set: local diff or PR)
# --------------------------------------------------------------------------- #
def cmd_review(args: argparse.Namespace) -> int:
    from cli.paths import project_root
    from cli.review_run import run_review
    from cli.runner import AgentRunner

    root = project_root()
    skills_dir = sigma_home() / "skills"
    target = getattr(args, "target", None)
    label = target or "local diff (HEAD)"
    _print(f"σ review — {label}")
    res = run_review(
        target,
        root,
        skills_dir,
        make_runner=lambda: AgentRunner(),
        ts=_now_iso(),
    )
    if res.skipped_reason:
        _print(f"  {res.skipped_reason}")
        return 0
    if not res.ok:
        _print(f"✗ review failed: {res.error}")
        return 1
    if res.report_path:
        _print(f"✓ wrote {res.report_path}")
    if res.domains:
        _print(f"  domains: {', '.join(res.domains)}")
    decision = res.gate
    if decision is not None:
        mark = "✅ PASS" if decision.passed else "❌ FAIL"
        _print(f"  verdict: {mark} — {decision.reason}")
    for p in res.ratcheted:
        _print(f"    ratcheted → {p}")
    if res.pr_comment:
        _print("  posted PR summary comment")
    # CI gate: --check exits non-zero on FAIL.
    if args.check and decision is not None and not decision.passed:
        return 1
    return 0


# --------------------------------------------------------------------------- #
# cost (report the cost ledger)
# --------------------------------------------------------------------------- #
def cmd_cost(args: argparse.Namespace) -> int:
    from cli.cost import ledger_path, read_ledger, report
    from cli.paths import project_root

    root = project_root()
    rows = read_ledger(ledger_path(root))
    _print(report(rows))
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
    pr.add_argument("--deep", action="store_true",
                    help="web-grounded deep research (exhaustive live web search; slower)")
    pr.add_argument("--web", action="store_true",
                    help="quick web-grounded pass (lighter than --deep; --deep wins if both)")
    pr.set_defaults(func=cmd_research)

    pl = sub.add_parser("loop", help="Autonomous loop planner/executor")
    pl.add_argument("--topic", required=True)
    pl.add_argument("--execute", action="store_true", help="run maker→checker cycles (default: plan only)")
    pl.add_argument("--tdd", action="store_true",
                    help="TDD: a distinct agent writes a failing test before the implementer")
    pl.add_argument("--team", action="store_true",
                    help="run independent tasks in parallel (each its own cycle)")
    pl.add_argument("--logic", action="store_true",
                    help="add the logic-evaluator axis (cycle passes only if logic also passes)")
    pl.add_argument("--keep-awake", action="store_true", help="prevent Mac sleep during the run (caffeinate)")
    pl.add_argument("--gate", help="wakeAgent script: skip the run if it reports nothing to do")
    pl.set_defaults(func=cmd_loop)

    ph = sub.add_parser("hermes", help="Conductor: route plain language to a stage and run it")
    ph.add_argument("message", help="what you want, in plain language")
    ph.add_argument("--topic", required=True, help="topic/slug locating the workspace")
    ph.add_argument("--auto", action="store_true", help="run the full chain, pausing only at human gates")
    ph.add_argument("--terse", action="store_true", help="compress output (caveman skill)")
    ph.add_argument("--keep-awake", action="store_true", help="prevent Mac sleep during the run (caffeinate)")
    ph.add_argument("--gate", help="wakeAgent script: skip a hop if it reports nothing to do")
    ph.set_defaults(func=cmd_hermes)

    pb = sub.add_parser("board", help="Kanban board over tasks + events")
    pb.add_argument("--topic", required=True, help="topic/slug locating the workspace")
    pb.add_argument("--watch", action="store_true", help="live redraw as agents progress")
    pb.set_defaults(func=cmd_board)

    pd = sub.add_parser("doctor", help="Diagnose (and optionally repair) the sigma install")
    pd.add_argument("--check", action="store_true", help="read-only; exit 1 if anything fails")
    pd.add_argument("--yes", action="store_true", help="apply all fixes without prompting")
    pd.add_argument("--update", action="store_true", help="pull sigma + re-vendor skills before checking")
    pd.set_defaults(func=cmd_doctor)

    po = sub.add_parser("onboard", help="Friendly first-run setup (domains, API keys, RTK)")
    po.add_argument("--name", help="project name")
    po.set_defaults(func=cmd_onboard)

    plearn = sub.add_parser("learn", help="Learn the codebase → ARCHITECTURE.md + a CodeTour")
    plearn.add_argument("--topic", help="slug for the .tour file (default: from tour title)")
    plearn.add_argument("--persona", help="who the walkthrough is for (e.g. 'new backend dev')")
    plearn.add_argument("--dry-run", action="store_true", help="print the invocation, do not run claude")
    plearn.set_defaults(func=cmd_learn)

    pw = sub.add_parser("weave", help="Weave stage artifacts → chain.html + chain.json")
    pw.add_argument("--topic", required=True, help="topic/slug locating the workspace")
    pw.add_argument("--dry-run", action="store_true", help="print the invocation, do not run claude")
    pw.set_defaults(func=cmd_weave)

    pprofile = sub.add_parser("profile", help="Walk the codebase → logic-profile.md (grounds review)")
    pprofile.add_argument("--dry-run", action="store_true", help="print the invocation, do not run claude")
    pprofile.set_defaults(func=cmd_profile)

    preview = sub.add_parser("review", help="Three-axis review of a change set (local diff or PR)")
    preview.add_argument("target", nargs="?",
                         help="PR number/URL, a git range (a..b), or empty for local diff vs HEAD")
    preview.add_argument("--check", action="store_true", help="exit 1 if the review gate FAILs (CI)")
    preview.set_defaults(func=cmd_review)

    pcost = sub.add_parser("cost", help="Report sigma's token-cost ledger")
    pcost.set_defaults(func=cmd_cost)

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
