#!/usr/bin/env python3
"""sigma — personal AI workflow toolkit CLI.

Wraps Claude Code with the sigma pipeline and a multi-model research phase.
See README.md and CLAUDE.md for the design and layout.
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
    record_cycle_steps,
    run_loop,
)
from cli.models import available_models
from cli.paths import DOMAINS, sigma_home, spec_workspace
from cli.research import claude_synthesis_runner, research, routed_synthesis_runner


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
    from cli.search_providers import available_tools

    cfg = load_config()
    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else cfg.models
    )
    tools = cfg.tools
    ws = spec_workspace(args.topic)
    deep = getattr(args, "deep", False)
    web = getattr(args, "web", False) and not deep  # deep wins if both given
    tag = "  [deep]" if deep else ("  [web]" if web else "")
    _print(f"sigma research — topic={args.topic!r}{tag}")
    _print(f"  models requested: {', '.join(models)}")
    avail = available_models(models)
    _print(f"  models available: {', '.join(avail) or '(none)'}")
    if tools:
        avail_tools = available_tools(tools)
        _print(f"  search tools requested: {', '.join(tools)}")
        _print(f"  search tools available: {', '.join(avail_tools) or '(none — API key not configured)'}")
    if deep:
        _print("  mode: deep (web-grounded — this may take a few minutes)")
    elif web:
        _print("  mode: web (quick web-grounded pass)")
    from cli.cost import routing_for

    if args.no_route:
        synthesis = claude_synthesis_runner
    else:
        synthesis_tier = routing_for("research")["synthesis"]
        synthesis = routed_synthesis_runner(synthesis_tier)
        _print(f"  🧭 routing: synthesis→{synthesis_tier}")
    out = research(
        args.topic, models, ws, requested_tools=tools, deep=deep, web=web,
        synthesis_runner=synthesis,
    )
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
    if args.codex_tdd and not (args.tdd or args.all):
        _print("✗ --codex-tdd requires --tdd (the test-writer role only exists in TDD mode)")
        return 1

    from cli.cost import routing_for
    from cli.keepawake import keep_awake
    from cli.models import clean_output, codex_argv_builder
    from cli.paths import project_root
    from cli.runner import AgentRunner
    from cli.trajectory import make_sink

    skills_dir = sigma_home() / "skills"
    # --all is shorthand for turning on every axis, including the two that stay
    # opt-in otherwise (tdd, team change the execution MODEL, not just add a
    # check — bigger behavior shift than the default-on correctness axes below).
    if args.all:
        args.tdd = True
        args.team = True
        args.logic = True
        args.simplify = True
        args.advisor = True
        args.e2e = True
        _print("  🎛️  --all: every axis on (tdd, team, logic, simplify, advisor, e2e)")
    if args.keep_awake:
        _print("  ☕ keep-awake on (caffeinate)")
    if args.tdd:
        _print("  🧪 TDD mode: a distinct agent writes a failing test before each implementer")
    if args.team:
        _print("  👥 team mode: independent tasks run in parallel")
        _print(f"  🌳 worktree isolation: {'on' if cfg.loop.worktrees else 'off (sigma.config.yml)'}")
    if args.logic:
        _print("  🧠 logic mode: a distinct logic-evaluator axis gates the cycle (--no-logic to disable)")
    if args.simplify:
        _print("  🧹 simplify mode: a distinct agent cleans up slop after each pass (re-verified) "
                "(--no-simplify to disable)")
    if args.e2e:
        _print("  🌐 e2e mode: a distinct agent drives each task's mapped BDD scenario live "
                "(FAIL blocks, ERROR doesn't) (--no-e2e to disable)")
    if args.advisor:
        _print(f"  🛟 advisor mode: on a verify/logic/e2e fail, a distinct advisor drafts a fix "
                f"(max {args.advisor_rounds} round(s); reverts on exhaustion) (--no-advisor to disable)")
    if args.codex_verify:
        _print("  🐙 codex-verify: verifier runs via codex (cross-provider maker≠checker)")
    if args.codex_tdd:
        _print("  🐙 codex-tdd: test-writer runs via codex")

    # Trajectory capture: every agent run appends a step to the workspace
    # (best-effort observability, never breaks a run).
    sink = make_sink(ws, ts=_now_iso())

    # Intelligent model routing is ON BY DEFAULT: mechanical roles (implement,
    # verify) → mid tier, reasoning roles (logic) → strong tier. --no-route
    # reproduces the old unrouted behavior byte-for-byte (model=None everywhere,
    # no --model injected into the agent argv). Per-role --model-* flags override
    # a single role's tier regardless of routing state. test-writer/simplifier
    # deliberately alias verify's/implement's tier (no dedicated routing key —
    # they are mechanical roles, same tier as the axis they extend).
    routes = {} if args.no_route else routing_for("loop")
    if args.model_implement:
        routes["implement"] = args.model_implement
    if args.model_verify:
        routes["verify"] = args.model_verify
    if args.model_logic:
        routes["logic"] = args.model_logic
    if args.no_route:
        _print("  🧭 routing: off (--no-route) — CLI default model for every role")
    else:
        _print(f"  🧭 routing: implement/verify→{routes['implement']}, logic→{routes['logic']}")

    # Advisor's model tier resolves INDEPENDENTLY of the routing dict above —
    # escalation's whole point is a stronger model, so it must not silently drop
    # to the base model just because --no-route was passed. Default: opus.
    advisor_model = args.model_advisor or routes.get("advisor") or "opus"

    # Parse spec.md's BDD scenarios ONCE up front (spec_scenarios is a plain
    # list passed to every cycle — execute_cycle never re-reads the file).
    # Parsed regardless of --e2e: the verify + logic prompts use a task's
    # mapped scenario as acceptance-criteria context even when the live e2e
    # axis is off. Missing spec.md → empty list (fail-safe: verify prompts
    # stay unchanged and every task's e2e step simply skips).
    from cli.scenarios import parse_scenarios

    spec_scenarios = []
    spec_file = ws / "spec.md"
    if spec_file.exists():
        spec_scenarios = parse_scenarios(spec_file.read_text())
    elif args.e2e:
        _print(f"  ⚠ --e2e given but no spec.md at {spec_file} — every task's e2e step will skip")

    def _make(role_tier: Optional[str]):
        return AgentRunner(model=role_tier, trajectory_sink=sink)

    def _make_codex(sandbox: str):
        return AgentRunner(
            executable="codex",
            argv_builder=codex_argv_builder(sandbox),
            output_cleaner=lambda raw: clean_output("gpt", raw),
            trajectory_sink=sink,
        )

    with keep_awake(enabled=args.keep_awake):
        outcomes = run_loop(
            tasks,
            ws,
            skills_dir,
            cfg.loop.max_cycles,
            make_implementer=lambda: _make(routes.get("implement")),
            make_verifier=(lambda: _make_codex("read-only")) if args.codex_verify else (lambda: _make(routes.get("verify"))),
            make_logic_checker=(lambda: _make(routes.get("logic"))) if args.logic else None,
            make_test_writer=(
                (lambda: _make_codex("workspace-write")) if (args.tdd and args.codex_tdd)
                else ((lambda: _make(routes.get("verify"))) if args.tdd else None)
            ),
            make_simplifier=(lambda: _make(routes.get("implement"))) if args.simplify else None,
            make_advisor=(lambda: _make(advisor_model)) if args.advisor else None,
            advisor_rounds=args.advisor_rounds,
            make_e2e_runner=(lambda: _make(routes.get("e2e"))) if args.e2e else None,
            spec_scenarios=spec_scenarios,
            team=args.team,
            worktrees=cfg.loop.worktrees,
            project_root=project_root(),
            gate=args.gate,
        )
    if not outcomes and args.gate:
        _print("  gate: nothing to do — skipped (0 tokens)")
        return 0
    # Record one "cycle" trajectory step per completed outcome — the real,
    # measured pass/fail signal `sigma trajectory --efficiency` reports on.
    record_cycle_steps(outcomes, sink)
    passed = sum(1 for o in outcomes if o.verified)
    _print(f"✓ ran {len(outcomes)} cycle(s): {passed} passed, {len(outcomes) - passed} failed")
    for o in outcomes:
        mark = "✓" if o.verified else "✗"
        _print(f"  {mark} {o.task_title}")
        if o.test_written is not None:
            _print(f"    test-first: {'✓ written' if o.test_written else '✗ failed'}")
        if o.regression_test:
            _print(f"    regression test pinned → {o.regression_test}")
        if o.simplified is not None:
            _print(f"    simplify: {'✓ applied (re-verified)' if o.simplified else '✗ skipped/reverted'}")
        if o.e2e_ok is not None:
            _print(f"    e2e: {'✓ passed' if o.e2e_ok else '✗ failed (blocked)'}")
        if o.advised is not None:
            rounds = o.advisor_rounds_used or 0
            _print(f"    advisor: {'✓ rescued in ' + str(rounds) + ' round(s)' if o.advised else '✗ exhausted (' + str(rounds) + ' round(s)) — reverted'}")
        if o.merge_conflict:
            _print(f"    ⚠ merge conflict — branch left at {o.merge_conflict} for manual resolution")
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
    from cli.trajectory import make_sink

    ws = spec_workspace(args.topic)
    ws.mkdir(parents=True, exist_ok=True)
    mode = "auto" if args.auto else "single-step"
    _print(f"σ hermes — topic={args.topic!r} mode={mode}{' terse' if args.terse else ''}")
    if args.keep_awake:
        _print("  ☕ keep-awake on (caffeinate)")
    sink = make_sink(ws, ts=_now_iso())
    from cli.cost import routing_for

    routes = {} if args.no_route else routing_for("hermes")
    if args.no_route:
        _print("  🧭 routing: off (--no-route) — CLI default model for every stage")
    else:
        _print("  🧭 routing: planning/grill stages→opus, execution stages→sonnet")
    with keep_awake(enabled=args.keep_awake):
        result = run_hermes(
            args.message,
            ws,
            auto=args.auto,
            terse=args.terse,
            make_runner=lambda model=None: AgentRunner(model=model, trajectory_sink=sink),
            now=_now_iso(),
            gate=args.gate,
            stage_routes=routes,
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
    from cli import render
    from cli.learn import existing_artifacts, run_learn
    from cli.paths import project_root

    root = project_root()
    _print(f"sigma learn — codebase at {root}")
    if args.persona:
        _print(f"  persona: {args.persona}")

    # Overwrite guard: sigma learn regenerates ARCHITECTURE.md + the tour. If a
    # prior run's artifacts exist, confirm before clobbering them (unless --force
    # or --dry-run). Skipped on a dry run (nothing is written).
    if not args.dry_run and not args.force:
        prior = existing_artifacts(root)
        if prior:
            _print("  ⚠ learn artifacts already exist:")
            for p in prior:
                _print(f"    - {p.relative_to(root)}")
            if not render.confirm("Regenerate and OVERWRITE them?"):
                _print("  aborted — kept existing artifacts (use --force to skip this prompt)")
                return 0
    res = run_learn(
        root,
        persona=args.persona,
        topic=args.topic,
        dry_run=args.dry_run,
        build_graph=not args.no_graph,
    )
    if res.graph_built:
        _print("  ✓ built knowledge graph (graphify)")
    elif res.graph_note:
        _print(f"  ℹ {res.graph_note}")
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
# session-context (print the learn-artifact pointer for a SessionStart hook)
# --------------------------------------------------------------------------- #
def cmd_session_context(args: argparse.Namespace) -> int:
    """Print the pointer to this repo's learn artifacts.

    Wired as a Claude Code SessionStart hook (its stdout is injected as session
    context). ALWAYS exits 0 and never raises — a session-start hook must never
    break a session (inverse of verify's default-FAIL: here we default to a
    harmless nudge). Errors degrade to the lazy hint.
    """
    try:
        from cli.paths import project_root
        from cli.session_context import build_pointer

        print(build_pointer(project_root()))
    except Exception:  # noqa: BLE001 — a hook must never propagate an error
        from cli.session_context import LAZY_HINT

        print(LAZY_HINT)
    return 0


# --------------------------------------------------------------------------- #
# setup-repo (one-shot per-repo bootstrap: config + hook + CLAUDE.local + map)
# --------------------------------------------------------------------------- #
def cmd_setup_repo(args: argparse.Namespace) -> int:
    from cli.paths import project_root
    from cli.setup_repo import run_setup_repo

    root = project_root()
    _print(f"sigma setup-repo — bootstrapping {root}")
    domains = [d.strip() for d in args.domains.split(",")] if args.domains else None
    if not args.no_learn:
        _print("  (will map the codebase with an agent — pass --no-learn to skip)")
    if not args.no_claude_md:
        _print("  (will scaffold or check CLAUDE.md — pass --no-claude-md to skip)")
    res = run_setup_repo(
        root, domains=domains, no_learn=args.no_learn, no_claude_md=args.no_claude_md
    )
    for step in res.steps:
        _print(f"  • {step}")
    _print("✓ repo ready — Claude will read this repo's architecture map each session")
    return 0


# --------------------------------------------------------------------------- #
# uninstall (reverse the installer: launcher + ~/.sigma + Claude plugin)
# --------------------------------------------------------------------------- #
def cmd_uninstall(args: argparse.Namespace) -> int:
    from cli import render
    from cli.uninstall import build_plan, run_uninstall

    plan = build_plan()
    if plan.nothing_to_do():
        _print("sigma is not installed (no launcher, install dir, or Claude CLI found).")
        return 0

    _print("sigma uninstall — will remove (each step confirmed):")
    if plan.launcher_exists:
        _print(f"  • launcher       {plan.launcher}")
    if plan.install_dir_exists:
        secret = "  ⚠ contains API keys (~/.sigma/.env)" if plan.has_secrets else ""
        _print(f"  • install dir    {plan.install_dir}{secret}")
    if plan.has_claude_cli:
        _print("  • Claude plugin  sigma@sigma + marketplace")
    _print("  (global RTK / caveman / statusline are left untouched — remove by hand if wanted)")

    res = run_uninstall(plan, confirm=render.confirm, assume_yes=args.yes)
    for r in res.removed:
        _print(f"  ✓ removed {r}")
    for s in res.skipped:
        _print(f"  – kept    {s}")
    for e in res.errors:
        _print(f"  ✗ {e}")
    _print("✓ uninstall complete" if not res.errors else "⚠ uninstall finished with errors")
    return 1 if res.errors else 0


# --------------------------------------------------------------------------- #
# scout (discover relevant skills on skillsmp.com → install on approval)
# --------------------------------------------------------------------------- #
def cmd_scout(args: argparse.Namespace) -> int:
    from cli import render
    from cli.paths import project_root
    from cli.scout_run import discover, install_hits

    cfg = load_config()
    domains = cfg.domains or list(DOMAINS)
    _print(f"σ scout — skillsmp.com, domains: {', '.join(domains)}")

    # Where vendored/installed skills already live, for dedup; and the install target.
    if args.vendor:
        skills_dir = sigma_home() / "skills"
        dest = skills_dir / "vendor"
        _print("  target: sigma bundle (skills/vendor/) — commit after review")
    else:
        skills_dir = project_root() / ".claude" / "skills"
        dest = skills_dir
        _print(f"  target: project skills ({dest})")

    res = discover(
        domains,
        category=args.category,
        recent=args.recent,
        skills_dir=skills_dir,
    )
    if not res.ok:
        _print(f"  ℹ {res.note}")
        return 1
    if not res.hits:
        _print(f"  ✓ {res.note or 'nothing new to add'}")
        return 0

    _print(f"\n{len(res.hits)} candidate skill(s) (relevance-ranked):\n")
    for i, h in enumerate(res.hits, 1):
        _print(f"  {i}. {h.name}  ★{h.stars}  [{h.github_url}]")
        if h.description:
            _print(f"     {h.description[:100]}")

    if args.dry_run:
        _print("\n--- dry run — nothing installed ---")
        return 0

    def _confirm(h) -> bool:
        return render.confirm(f"Install '{h.name}' from {h.github_url}? (check its license)")

    installed = install_hits(res.hits, dest, confirm=_confirm)
    _print(f"\n✓ installed {len(installed)} skill(s) into {dest}")
    if args.vendor and installed:
        _print("  → review + commit the new skills into the sigma bundle")
    return 0


# --------------------------------------------------------------------------- #
# prune (surface loaded-but-unused MCP/plugins → reversible disable)
# --------------------------------------------------------------------------- #
def cmd_prune(args: argparse.Namespace) -> int:
    from cli import render
    from cli.paths import project_root
    from cli.prune import KIND_MCP_USER
    from cli.prune_run import build_report, disable_plugins

    root = project_root()
    project_mcp = root / ".mcp.json"
    _print("σ prune — loaded MCP servers + plugins vs recent usage")

    rep = build_report(
        project_mcp_path=project_mcp if project_mcp.exists() else None,
        max_files=args.files,
        recent_files=args.recent_files,
        idle_threshold=args.idle_threshold,
    )
    if not rep.candidates:
        _print(f"  ✓ {rep.note or 'nothing to prune'}")
        return 0

    _print(
        f"\n{len(rep.candidates)} loaded-but-unused item(s) "
        f"(~{rep.freed_tokens:,} ctx tokens, scanned {rep.scanned_files} transcript(s)):\n"
    )
    for i, c in enumerate(rep.candidates, 1):
        tag = "" if c.reversible else "  (manual: user-level MCP)"
        conf = f"  ⚠ rarely used ({c.uses}× — judgment call)" if c.low_confidence else ""
        _print(f"  {i}. [{c.kind}] {c.name}  ~{c.weight:,} tok{tag}{conf}")

    if args.check:
        # CI/read-only: exit 1 to flag that prunable bloat exists.
        _print("\n(--check) prunable items found — not disabling")
        return 1

    # Only plugins are reversibly disableable via settings.json. User-level MCP
    # servers live in ~/.claude.json and are surfaced for a manual edit (we never
    # touch that file automatically).
    plugins = [c.name for c in rep.candidates if c.reversible and c.kind != KIND_MCP_USER]
    if not plugins:
        _print("\n  ℹ only user-level MCP servers found — disable those manually in ~/.claude.json")
        return 0

    if args.yes:
        chosen = plugins
    else:
        chosen = [n for n in plugins
                  if render.confirm(f"Disable '{n}'? (reversible — re-enable anytime)")]
    if not chosen:
        _print("\n  nothing disabled")
        return 0

    if disable_plugins(chosen):
        _print(f"\n✓ disabled {len(chosen)} plugin(s) in settings.json (reversible — restart Claude Code)")
    else:
        _print("\n✗ could not write settings.json")
        return 1
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
# claude-md-check (check CLAUDE.md / CLAUDE.local.md against best-practice research)
# --------------------------------------------------------------------------- #
def cmd_claude_md_check(args: argparse.Namespace) -> int:
    from cli.claude_md_check_run import run_check, write_report
    from cli.paths import project_root

    root = project_root()
    _print(f"σ claude-md-check — {root}")
    res = run_check(root)
    if not res.ok:
        _print(f"✗ {res.error}")
        return 1
    _print(f"  checked: {', '.join(res.files_checked)}")
    for f in res.findings:
        _print(f"  {f.render()}")
    if not res.findings:
        _print("  ✓ no findings")
    decision = res.gate
    mark = "✅ PASS" if decision.passed else "❌ FAIL"
    _print(f"  verdict: {mark} — {decision.reason}")
    out = write_report(root, res.report)
    _print(f"✓ wrote {out}")
    if args.check and not decision.passed:
        return 1
    return 0


# --------------------------------------------------------------------------- #
# claude-md-create (scaffold a best-practice-shaped CLAUDE.md / CLAUDE.local.md)
# --------------------------------------------------------------------------- #
def cmd_claude_md_create(args: argparse.Namespace) -> int:
    from cli.claude_md_scaffold_run import run_scaffold
    from cli.paths import project_root

    root = project_root()
    _print(f"σ claude-md-create — target={args.target} at {root}")
    res = run_scaffold(root, target=args.target, force=args.force, dry_run=args.dry_run)
    if args.dry_run:
        _print("--- invocation (dry run) ---")
        _print(res.prompt)
        return 0
    if not res.ok:
        _print(f"✗ {res.error}")
        return 1
    if res.used_skeleton_fallback:
        _print("  ⚠ agent pass did not produce usable content — wrote the static skeleton")
    _print(f"✓ wrote {res.path}")
    return 0


# --------------------------------------------------------------------------- #
# eval (run an eval set, LM-judge each case, gate at a threshold)
# --------------------------------------------------------------------------- #
def cmd_eval(args: argparse.Namespace) -> int:
    from cli.cost import routing_for
    from cli.eval_run import eval_set_path, run_eval
    from cli.paths import project_root
    from cli.runner import AgentRunner
    from cli.trajectory import make_sink

    root = project_root()
    name = args.set
    _print(f"σ eval — set={name!r} threshold={args.threshold}")
    if not eval_set_path(root, name).exists():
        _print(f"✗ no eval set at {eval_set_path(root, name)}")
        _print("  create sigma/evals/<name>.md (see commands/eval.md for the format)")
        return 1

    # Trajectory sink lives in the eval set's report dir.
    ws = root / "sigma" / "evals" / name
    sink = make_sink(ws, ts=_now_iso())
    routes = routing_for("eval") if args.route else {}
    if args.route:
        _print(f"  🧭 routing: sut→{routes['sut']}, judge→{routes['judge']}")

    artifact = Path(args.artifact).expanduser() if args.artifact else None
    res = run_eval(
        name,
        root,
        make_sut=lambda: AgentRunner(model=routes.get("sut"), trajectory_sink=sink),
        make_grader=lambda: AgentRunner(model=routes.get("judge"), trajectory_sink=sink),
        threshold=args.threshold,
        artifact=artifact,
        ts=_now_iso(),
    )
    if res.skipped_reason:
        _print(f"  {res.skipped_reason}")
        return 0
    if not res.ok:
        _print(f"✗ eval failed: {res.error}")
        return 1
    if res.report_path:
        _print(f"✓ wrote {res.report_path}")
    decision = res.gate
    if decision is not None:
        mark = "✅ PASS" if decision.passed else "❌ FAIL"
        _print(f"  verdict: {mark} — {decision.reason}")
    if args.check and decision is not None and not decision.passed:
        return 1
    return 0


# --------------------------------------------------------------------------- #
# trajectory (observe what agents actually did in a workspace)
# --------------------------------------------------------------------------- #
def cmd_trajectory(args: argparse.Namespace) -> int:
    from cli.trajectory import efficiency_report, read_steps, summarize

    ws = spec_workspace(args.topic)
    if not ws.exists():
        _print(f"✗ no spec workspace at {ws}. Run a loop or hermes first.")
        return 1
    steps = read_steps(ws)
    if args.efficiency:
        _print(efficiency_report(steps))
        return 0
    summary = summarize(steps)
    if args.json:
        import json
        from dataclasses import asdict

        _print(json.dumps(asdict(summary), sort_keys=True))
    else:
        _print(summary.render())
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
# usage (thin ccusage wrapper — real Claude Code session token/cache/cost)
# --------------------------------------------------------------------------- #
def _usage_spawn(argv: List[str]) -> int:
    """Run ccusage interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def cmd_usage(args: argparse.Namespace) -> int:
    from cli.usage import MISSING_NODE_MESSAGE, build_argv, node_runtime_available

    if not node_runtime_available():
        _print(MISSING_NODE_MESSAGE)
        return 0
    passthrough = list(getattr(args, "usage_args", None) or [])
    return _usage_spawn(build_argv(passthrough))


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
    pr.add_argument("--no-route", action="store_true",
                    help="disable synthesis model routing (default: synthesis→strong tier)")
    pr.set_defaults(func=cmd_research)

    pl = sub.add_parser("loop", help="Autonomous loop planner/executor")
    pl.add_argument("--topic", required=True)
    pl.add_argument("--execute", action="store_true", help="run maker→checker cycles (default: plan only)")
    pl.add_argument("--all", action="store_true",
                    help="turn on every axis: tdd, team, logic, simplify, advisor, e2e")
    pl.add_argument("--tdd", action="store_true",
                    help="TDD: a distinct agent writes a failing test before the implementer "
                         "(opt-in; also turned on by --all)")
    pl.add_argument("--team", action="store_true",
                    help="run independent tasks in parallel (each its own cycle) "
                         "(opt-in; also turned on by --all)")
    pl.add_argument("--logic", dest="logic", action="store_true", default=True,
                    help="the logic-evaluator axis: cycle passes only if logic also passes "
                         "(default ON; see --no-logic)")
    pl.add_argument("--no-logic", dest="logic", action="store_false",
                    help="disable the logic-evaluator axis")
    pl.add_argument("--simplify", dest="simplify", action="store_true", default=True,
                    help="after each pass, a distinct agent cleans up AI slop (re-verified to "
                         "preserve behaviour) (default ON; see --no-simplify)")
    pl.add_argument("--no-simplify", dest="simplify", action="store_false",
                    help="disable the post-pass simplify cleanup")
    pl.add_argument("--route", action="store_true",
                    help="deprecated, no-op: routing is now on by default (see --no-route)")
    pl.add_argument("--no-route", action="store_true",
                    help="disable model routing; run every role on the CLI's default model")
    pl.add_argument("--model-implement", help="override the model alias for the implementer role")
    pl.add_argument("--model-verify", help="override the model alias for the verifier role")
    pl.add_argument("--model-logic", help="override the model alias for the logic-evaluator role")
    pl.add_argument("--model-advisor", help="override the model alias for the advisor role (default: opus)")
    pl.add_argument("--advisor", dest="advisor", action="store_true", default=True,
                    help="on a verify/logic/e2e fail, a distinct advisor drafts a correction plan and "
                         "the implementer retries (re-verified; reverts to the original on exhaustion) "
                         "(default ON; see --no-advisor)")
    pl.add_argument("--no-advisor", dest="advisor", action="store_false",
                    help="disable the advisor escalation")
    pl.add_argument("--advisor-rounds", type=int, default=1,
                    help="max advisor→retry→re-verify rounds per cycle before ratcheting (default 1)")
    pl.add_argument("--e2e", dest="e2e", action="store_true", default=True,
                    help="drive each task's mapped BDD scenario live (Given/When/Then) after "
                         "verify+logic pass; a real behavioral FAIL blocks the cycle, an ERROR "
                         "(app unreachable) does not (default ON; see --no-e2e)")
    pl.add_argument("--no-e2e", dest="e2e", action="store_false",
                    help="disable the live e2e scenario gate")
    pl.add_argument("--keep-awake", action="store_true", help="prevent Mac sleep during the run (caffeinate)")
    pl.add_argument("--gate", help="wakeAgent script: skip the run if it reports nothing to do")
    pl.add_argument("--codex-verify", action="store_true",
                     help="run the verifier role via the codex CLI instead of claude "
                          "(genuine cross-provider maker≠checker)")
    pl.add_argument("--codex-tdd", action="store_true",
                     help="run the TDD test-writer role via the codex CLI instead of claude "
                          "(requires --tdd)")
    pl.set_defaults(func=cmd_loop)

    ph = sub.add_parser("hermes", help="Conductor: route plain language to a stage and run it")
    ph.add_argument("message", help="what you want, in plain language")
    ph.add_argument("--topic", required=True, help="topic/slug locating the workspace")
    ph.add_argument("--auto", action="store_true", help="run the full chain, pausing only at human gates")
    ph.add_argument("--terse", action="store_true", help="compress output (caveman skill)")
    ph.add_argument("--keep-awake", action="store_true", help="prevent Mac sleep during the run (caffeinate)")
    ph.add_argument("--gate", help="wakeAgent script: skip a hop if it reports nothing to do")
    ph.add_argument("--no-route", action="store_true",
                    help="disable per-stage model routing (default: planning/grill→strong, execution→mid)")
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
    plearn.add_argument("--no-graph", action="store_true",
                        help="skip the graphify knowledge-graph build (on by default when installed)")
    plearn.add_argument("--force", action="store_true",
                        help="overwrite existing ARCHITECTURE.md / .tours without prompting")
    plearn.set_defaults(func=cmd_learn)

    psc = sub.add_parser("session-context",
                         help="Print the learn-artifact pointer (wired as a SessionStart hook)")
    psc.set_defaults(func=cmd_session_context)

    pun = sub.add_parser("uninstall",
                         help="Remove sigma: launcher + ~/.sigma + Claude plugin (confirm-gated)")
    pun.add_argument("--yes", action="store_true", help="remove all surfaces without prompting")
    pun.set_defaults(func=cmd_uninstall)

    psr = sub.add_parser("setup-repo",
                         help="Bootstrap THIS repo: config + SessionStart hook + CLAUDE.local + codebase map")
    psr.add_argument("--domains", help="comma list for sigma.config.yml (default: all) — only if config is missing")
    psr.add_argument("--no-learn", action="store_true",
                     help="skip building the codebase map (no agent run)")
    psr.add_argument("--no-claude-md", action="store_true",
                     help="skip scaffolding/checking CLAUDE.md")
    psr.set_defaults(func=cmd_setup_repo)

    pscout = sub.add_parser("scout", help="Discover relevant skills on skillsmp.com → install on approval")
    pscout.add_argument("--vendor", action="store_true",
                        help="install into sigma's own skills/vendor/ (maintainer mode) instead of the project")
    pscout.add_argument("--category", help="skillsmp category slug to filter by (default: per-domain)")
    pscout.add_argument("--recent", action="store_true", help="sort by recently-added instead of stars")
    pscout.add_argument("--dry-run", action="store_true", help="show candidates, install nothing")
    pscout.set_defaults(func=cmd_scout)

    pprune = sub.add_parser("prune", help="Surface loaded-but-unused MCP/plugins → reversible disable")
    pprune.add_argument("--check", action="store_true", help="read-only; exit 1 if prunable bloat exists (CI)")
    pprune.add_argument("--yes", action="store_true", help="disable all prunable plugins without prompting")
    pprune.add_argument("--files", type=int, default=40, help="how many recent transcripts to scan (schema width)")
    pprune.add_argument("--recent-files", type=int, default=None,
                        help="usage window: prune items idle in the last N transcripts (default: all scanned)")
    pprune.add_argument("--idle-threshold", type=int, default=0,
                        help="also surface items used ≤N times as low-confidence candidates (default 0 = unused only)")
    pprune.set_defaults(func=cmd_prune)

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

    pcmc = sub.add_parser("claude-md-check",
                          help="Check CLAUDE.md / CLAUDE.local.md against best-practice research")
    pcmc.add_argument("--check", action="store_true", help="exit 1 if the check gate FAILs (CI)")
    pcmc.set_defaults(func=cmd_claude_md_check)

    pcmcr = sub.add_parser("claude-md-create",
                           help="Scaffold a best-practice-shaped CLAUDE.md / CLAUDE.local.md")
    pcmcr.add_argument("--target", choices=["repo", "local"], default="repo",
                       help="repo → CLAUDE.md (team-shared), local → CLAUDE.local.md (personal, gitignored)")
    pcmcr.add_argument("--force", action="store_true", help="overwrite an existing file")
    pcmcr.add_argument("--dry-run", action="store_true", help="print the invocation, do not run claude")
    pcmcr.set_defaults(func=cmd_claude_md_create)

    pcost = sub.add_parser("cost", help="Report sigma's token-cost ledger")
    pcost.set_defaults(func=cmd_cost)

    pu = sub.add_parser(
        "usage",
        help="Claude Code token/cache/cost usage (wraps ccusage)",
    )
    # NOTE: main() intercepts raw argv for "usage" BEFORE parse_args ever runs
    # (see main()'s docstring-comment there) — a flag-first passthrough like
    # `sigma usage --json` would otherwise hit argparse's known REMAINDER
    # limitation and raise SystemExit(2) instead of reaching ccusage. This
    # REMAINDER declaration is therefore dead on the real invocation path; it
    # is kept only so `sigma --help` / `sigma usage --help` (top-level
    # listing) still shows `usage` with its passthrough-args hint.
    pu.add_argument("usage_args", nargs=argparse.REMAINDER, help="passthrough args for ccusage")
    pu.set_defaults(func=cmd_usage)

    ptraj = sub.add_parser("trajectory", help="Observe agent steps recorded in a workspace")
    ptraj.add_argument("--topic", required=True, help="topic/slug locating the workspace")
    ptraj.add_argument("--json", action="store_true", help="emit the summary as JSON")
    ptraj.add_argument("--efficiency", action="store_true",
                        help="report cycle pass rate + escalation rate (real, measured signals)")
    ptraj.set_defaults(func=cmd_trajectory)

    peval = sub.add_parser("eval", help="Run an eval set, LM-judge each case, gate at a threshold")
    peval.add_argument("--set", required=True, help="eval set name (sigma/evals/<name>.md)")
    peval.add_argument("--threshold", type=float, default=0.8,
                       help="pass-rate bar the gate requires (default 0.8)")
    peval.add_argument("--artifact",
                       help="grade an existing file's text against each case (skip the SUT run)")
    peval.add_argument("--route", action="store_true",
                       help="intelligent model routing: judge→strong tier")
    peval.add_argument("--check", action="store_true", help="exit 1 if the eval gate FAILs (CI)")
    peval.set_defaults(func=cmd_eval)

    plaunch = sub.add_parser("launch", help="Open Claude Code with sigma context")
    plaunch.add_argument("--no-launch", action="store_true", help="print context, do not launch")
    plaunch.set_defaults(func=cmd_launch)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    # `usage` is a pure passthrough to ccusage: everything after `usage` is
    # forwarded verbatim (see cli/usage.py::build_argv). argparse's REMAINDER
    # (used on the `usage` subparser below, kept only so `sigma --help` still
    # lists `usage`) has a well-known limitation: if the FIRST passthrough
    # token looks like an option (`-`/`--` prefix, e.g. `sigma usage --json`),
    # argparse's own optional-argument matching intercepts it BEFORE
    # REMAINDER can claim it, raising SystemExit(2) ("unrecognized
    # arguments") instead of forwarding it. This is not fixable by tweaking
    # REMAINDER itself, so we bypass argparse entirely for this one
    # subcommand: take raw argv, and if its first token is "usage", forward
    # everything after it untouched — no reinterpretation, no flag matching.
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "usage":
        return cmd_usage(argparse.Namespace(usage_args=raw[1:]))

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # Default action: launch.
        return cmd_launch(argparse.Namespace(no_launch=True))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
