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
        confirm=render.confirm,
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
    if res.claude_md_ref_added:
        _print("  ✓ added ARCHITECTURE.md reference to CLAUDE.md")
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
# docs-check (cross-surface consistency: version parity + stale test counts)
# --------------------------------------------------------------------------- #
def cmd_docs_check(args: argparse.Namespace) -> int:
    from cli.docs_check_run import run_docs_check, write_report
    from cli.paths import project_root

    root = project_root()
    _print(f"σ docs-check — {root}")
    res = run_docs_check(root)
    if not res.ok:
        _print(f"✗ {res.error}")
        return 1
    _print(f"  checked: {', '.join(res.files_checked)}")
    if res.real_count is not None:
        _print(f"  real collected test count: {res.real_count}")
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

    # spec→eval bridge: --from-spec renders the topic's BDD scenarios into an
    # eval set (derived — spec.md stays the source of truth) and stops there.
    if args.from_spec:
        from cli.scenarios import parse_scenarios, render_eval_set

        ws = spec_workspace(args.from_spec)
        spec_file = ws / "spec.md"
        if not spec_file.exists():
            _print(f"✗ no spec.md at {spec_file}. Run /spec first.")
            return 1
        scenarios = parse_scenarios(spec_file.read_text())
        if not scenarios:
            _print("✗ spec.md has no Scenario/Given/When/Then blocks — nothing to generate")
            return 1
        set_name = args.set or ws.name
        out = eval_set_path(root, set_name)
        if out.exists() and not args.force:
            _print(f"✗ {out} already exists — pass --force to regenerate")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_eval_set(args.from_spec, scenarios))
        _print(f"✓ wrote {out} ({len(scenarios)} case(s) from spec scenarios)")
        _print(f"→ next: sigma eval --set {set_name}")
        return 0

    if not args.set:
        _print("✗ --set is required (or --from-spec <topic> to generate one)")
        return 1
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
        make_sut=lambda: AgentRunner(model=routes.get("sut"), trajectory_sink=sink, telemetry=True),
        make_grader=lambda: AgentRunner(model=routes.get("judge"), trajectory_sink=sink, telemetry=True),
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
    if getattr(args, "economy", False):
        from cli.axis_economy import build_economy

        economy = build_economy(steps)
        if args.json:
            import json
            from dataclasses import asdict

            _print(json.dumps(asdict(economy), sort_keys=True))
        else:
            _print(economy.render())
        return 0
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
# lessons (lesson-efficacy report + reversible archive of unused lessons)
# --------------------------------------------------------------------------- #
def cmd_lessons(args: argparse.Namespace) -> int:
    from cli import render
    from cli.lessons import archive_lesson, efficacy, list_domain_lessons, render_report
    from cli.paths import project_root
    from cli.trajectory import read_steps

    # Evidence scope: by default aggregate EVERY spec workspace's trajectory —
    # lessons are global (sigma_home()/skills), so judging them on one topic's
    # runs would offer to archive a lesson that other topics recall constantly
    # (violates never-act-on-absent-evidence). --topic restricts deliberately.
    if args.topic:
        workspaces = [spec_workspace(args.topic)]
        if not workspaces[0].exists():
            _print(f"✗ no spec workspace at {workspaces[0]}. Run a loop first.")
            return 1
    else:
        specs_root = project_root() / "sigma" / "specs"
        workspaces = sorted(d for d in specs_root.glob("*") if d.is_dir()) if specs_root.exists() else []
        if not workspaces:
            _print(f"✗ no spec workspaces under {specs_root}. Run a loop first.")
            return 1
    steps = []
    for ws in workspaces:
        steps.extend(read_steps(ws))
    _print(f"σ lessons — evidence from {len(workspaces)} workspace(s)")
    skills_dir = sigma_home() / "skills"
    report = efficacy(steps, list_domain_lessons(skills_dir))
    _print(render_report(report))

    if not args.archive:
        return 0
    if not report.has_recall_evidence:
        _print("\n(--archive) no recall evidence — nothing is archived on absent evidence")
        return 0
    if not report.no_evidence:
        _print("\n(--archive) no archive candidates")
        return 0
    archived = 0
    for stats in report.no_evidence:
        if render.confirm(f"Archive lesson '{stats.slug}' → skills/archive/? (reversible)"):
            dest = archive_lesson(skills_dir, stats.slug)
            if dest is not None:
                _print(f"  ✓ archived → {dest}")
                archived += 1
            else:
                _print(f"  ✗ could not archive '{stats.slug}' (missing or target exists)")
    _print(f"✓ archived {archived} lesson(s)")
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

    pdc = sub.add_parser("docs-check",
                         help="Cross-surface consistency: version parity + stale test counts")
    pdc.add_argument("--check", action="store_true", help="exit 1 if the gate FAILs (CI)")
    pdc.set_defaults(func=cmd_docs_check)

    pcmcr = sub.add_parser("claude-md-create",
                           help="Scaffold a best-practice-shaped CLAUDE.md / CLAUDE.local.md")
    pcmcr.add_argument("--target", choices=["repo", "local"], default="repo",
                       help="repo → CLAUDE.md (team-shared), local → CLAUDE.local.md (personal, gitignored)")
    pcmcr.add_argument("--force", action="store_true", help="overwrite an existing file")
    pcmcr.add_argument("--dry-run", action="store_true", help="print the invocation, do not run claude")
    pcmcr.set_defaults(func=cmd_claude_md_create)

    plessons = sub.add_parser("lessons",
                              help="Lesson-efficacy report (working / not-working / no-evidence)")
    plessons.add_argument("--topic",
                          help="restrict evidence to one topic's workspace (default: aggregate ALL workspaces)")
    plessons.add_argument("--archive", action="store_true",
                          help="offer to move never-recalled lessons to skills/archive/ (confirm-gated, reversible)")
    plessons.set_defaults(func=cmd_lessons)

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
    ptraj.add_argument("--economy", action="store_true",
                        help="per-axis token economy: tokens-per-value-event, idle-axis prune candidates")
    ptraj.set_defaults(func=cmd_trajectory)

    peval = sub.add_parser("eval", help="Run an eval set, LM-judge each case, gate at a threshold")
    peval.add_argument("--set", help="eval set name (sigma/evals/<name>.md)")
    peval.add_argument("--from-spec", dest="from_spec",
                       help="generate the eval set from a topic's spec.md BDD scenarios, then exit")
    peval.add_argument("--force", action="store_true",
                       help="with --from-spec: overwrite an existing generated set")
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
