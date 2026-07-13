import argparse
import os
import subprocess
import sys
from pathlib import Path

from cli.main import build_parser, cmd_init

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_version_subprocess():
    res = run_cli("--version")
    assert res.returncode == 0
    assert "sigma" in res.stdout


def test_help_lists_commands():
    res = run_cli("--help")
    assert "research" in res.stdout
    assert "loop" in res.stdout
    assert "init" in res.stdout


def test_parser_init_defaults():
    args = build_parser().parse_args(["init"])
    assert args.command == "init"


def test_cmd_init_writes_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import argparse

    ns = argparse.Namespace(name="t", domains="nlp,rl", force=False)
    rc = cmd_init(ns)
    assert rc == 0
    assert (tmp_path / "sigma.config.yml").exists()


def test_cmd_init_rejects_unknown_domain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import argparse

    ns = argparse.Namespace(name="t", domains="bogus", force=False)
    assert cmd_init(ns) == 1


def test_cmd_init_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import argparse

    ns = argparse.Namespace(name="t", domains="nlp", force=False)
    assert cmd_init(ns) == 0
    # second run without force should refuse
    assert cmd_init(ns) == 1


def test_stage_subcommands_retired(tmp_path, monkeypatch):
    # Plugin-first pivot: per-stage CLI wrappers (propose..verify) are retired.
    # Those flows live only as plugin slash commands now. The CLI must reject
    # them rather than shelling out an amnesiac subprocess.
    monkeypatch.chdir(tmp_path)
    # All six retired stages (full set from the design spec).
    for stage in ("propose", "blueprint", "spec", "tasks", "implement-task", "verify"):
        res = run_cli(stage, "--topic", "demo", "--dry-run")
        assert res.returncode != 0, f"{stage} should be retired from the CLI"


def _subcommands():
    """The registered CLI subcommand names (from the argparse choices)."""
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_help_omits_retired_stages():
    commands = _subcommands()
    # No retired stage wrapper may be a registered CLI subcommand.
    for stage in ("propose", "blueprint", "spec", "tasks", "implement-task", "verify"):
        assert stage not in commands, f"{stage} must not be a CLI subcommand"
    # But the kept commands remain.
    assert {"research", "loop", "hermes", "board", "weave"} <= commands


def test_help_lists_hermes_and_board():
    res = run_cli("--help")
    assert "hermes" in res.stdout
    assert "board" in res.stdout


def test_parser_hermes_flags():
    args = build_parser().parse_args(
        ["hermes", "build it", "--topic", "demo", "--auto", "--terse"]
    )
    assert args.command == "hermes"
    assert args.message == "build it"
    assert args.auto is True
    assert args.terse is True


def test_parser_board_watch_flag():
    args = build_parser().parse_args(["board", "--topic", "demo", "--watch"])
    assert args.command == "board"
    assert args.watch is True


def test_parser_loop_routing_defaults():
    # --route is a deprecated no-op (kept for backward compat); routing is on by
    # default now, so the real switch is --no-route.
    a = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--route"])
    assert a.command == "loop"
    assert a.route is True
    assert a.no_route is False
    b = build_parser().parse_args(["loop", "--topic", "demo"])
    assert b.route is False
    assert b.no_route is False
    c = build_parser().parse_args(["loop", "--topic", "demo", "--no-route"])
    assert c.no_route is True


def test_parser_loop_per_role_model_overrides():
    a = build_parser().parse_args([
        "loop", "--topic", "demo",
        "--model-implement", "haiku", "--model-verify", "sonnet",
        "--model-logic", "opus", "--model-advisor", "fable",
    ])
    assert a.model_implement == "haiku"
    assert a.model_verify == "sonnet"
    assert a.model_logic == "opus"
    assert a.model_advisor == "fable"


def test_parser_loop_advisor_flags():
    a = build_parser().parse_args(["loop", "--topic", "demo", "--advisor", "--advisor-rounds", "3"])
    assert a.advisor is True
    assert a.advisor_rounds == 3
    # advisor defaults ON; --no-advisor opts out.
    b = build_parser().parse_args(["loop", "--topic", "demo"])
    assert b.advisor is True
    assert b.advisor_rounds == 1
    c = build_parser().parse_args(["loop", "--topic", "demo", "--no-advisor"])
    assert c.advisor is False


def test_parser_trajectory():
    a = build_parser().parse_args(["trajectory", "--topic", "demo", "--json"])
    assert a.command == "trajectory"
    assert a.topic == "demo"
    assert a.json is True
    assert a.efficiency is False


def test_parser_trajectory_efficiency_flag():
    a = build_parser().parse_args(["trajectory", "--topic", "demo", "--efficiency"])
    assert a.efficiency is True


def test_cmd_trajectory_efficiency_no_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("trajectory", "--topic", "nonexistent", "--efficiency")
    assert res.returncode == 1


def test_help_lists_trajectory_and_eval():
    res = run_cli("--help")
    assert "trajectory" in res.stdout
    assert "eval" in res.stdout


def test_help_lists_doctor_and_onboard():
    res = run_cli("--help")
    assert "doctor" in res.stdout
    assert "onboard" in res.stdout


def test_parser_doctor_flags():
    a = build_parser().parse_args(["doctor", "--check", "--yes", "--update"])
    assert a.command == "doctor"
    assert a.check is True
    assert a.yes is True
    assert a.update is True


def test_parser_onboard():
    a = build_parser().parse_args(["onboard", "--name", "proj"])
    assert a.command == "onboard"
    assert a.name == "proj"


def test_parser_learn_no_graph_flag():
    a = build_parser().parse_args(["learn", "--no-graph"])
    assert a.command == "learn"
    assert a.no_graph is True
    b = build_parser().parse_args(["learn"])
    assert b.no_graph is False  # graph on by default


def test_parser_scout_flags():
    a = build_parser().parse_args(["scout", "--vendor", "--recent", "--dry-run"])
    assert a.command == "scout"
    assert a.vendor is True
    assert a.recent is True
    assert a.dry_run is True
    b = build_parser().parse_args(["scout"])
    assert b.vendor is False and b.recent is False


def test_help_lists_scout():
    res = run_cli("--help")
    assert "scout" in res.stdout


def test_parser_prune_flags():
    a = build_parser().parse_args(["prune", "--check", "--yes", "--files", "10"])
    assert a.command == "prune"
    assert a.check is True
    assert a.yes is True
    assert a.files == 10
    b = build_parser().parse_args(["prune"])
    assert b.files == 40  # default lookback
    assert b.recent_files is None  # default: usage window = full scan
    assert b.idle_threshold == 0   # default: unused-only
    c = build_parser().parse_args(["prune", "--recent-files", "5", "--idle-threshold", "1"])
    assert c.recent_files == 5
    assert c.idle_threshold == 1


def test_help_lists_prune():
    res = run_cli("--help")
    assert "prune" in res.stdout


def test_parser_gate_flags():
    a = build_parser().parse_args(["loop", "--topic", "d", "--gate", "check.py"])
    assert a.gate == "check.py"
    b = build_parser().parse_args(["hermes", "go", "--topic", "d", "--gate", "g.sh"])
    assert b.gate == "g.sh"
    # default None
    c = build_parser().parse_args(["loop", "--topic", "d"])
    assert c.gate is None


def test_parser_keep_awake_flags():
    a = build_parser().parse_args(["hermes", "go", "--topic", "d", "--keep-awake"])
    assert a.keep_awake is True
    b = build_parser().parse_args(["loop", "--topic", "d", "--execute", "--keep-awake"])
    assert b.keep_awake is True
    # default off
    c = build_parser().parse_args(["loop", "--topic", "d"])
    assert c.keep_awake is False


def test_board_missing_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("board", "--topic", "nope")
    assert res.returncode == 1
    assert "no spec workspace" in res.stdout


# --------------------------------------------------------------------------- #
# profile / review / cost subcommands
# --------------------------------------------------------------------------- #
def test_help_lists_profile_review_cost():
    res = run_cli("--help")
    for cmd in ("profile", "review", "cost"):
        assert cmd in res.stdout


def test_parser_review_target_and_check():
    a = build_parser().parse_args(["review", "42", "--check"])
    assert a.target == "42"
    assert a.check is True
    b = build_parser().parse_args(["review"])
    assert b.target is None
    assert b.check is False


def test_parser_profile_dry_run():
    a = build_parser().parse_args(["profile", "--dry-run"])
    assert a.dry_run is True


def test_cmd_cost_empty_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("cost")
    assert res.returncode == 0
    assert "No cost data yet" in res.stdout


def test_cmd_profile_dry_run_prints_invocation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("profile", "--dry-run")
    assert res.returncode == 0
    assert "ML-logic invariants" in res.stdout


# --------------------------------------------------------------------------- #
# session-context (SessionStart hook command — must always exit 0)
# --------------------------------------------------------------------------- #
def _run_cli_in(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        cwd=cwd,  # run in the temp project, not the sigma repo
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def test_cmd_session_context_lazy_hint(tmp_path):
    # Mark tmp_path as a project root so project_root() stops here, not the
    # real sigma repo (which has its own ARCHITECTURE.md).
    (tmp_path / "sigma.config.yml").write_text("name: t\ndomains: [nlp]\n")
    res = _run_cli_in(tmp_path, "session-context")
    assert res.returncode == 0
    assert "/learn" in res.stdout  # no artifacts → lazy hint


def test_cmd_session_context_points_to_artifacts(tmp_path):
    (tmp_path / "sigma.config.yml").write_text("name: t\ndomains: [nlp]\n")
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n")
    tours = tmp_path / ".tours"
    tours.mkdir()
    (tours / "x.tour").write_text("{}")
    res = _run_cli_in(tmp_path, "session-context")
    assert res.returncode == 0
    assert "ARCHITECTURE.md" in res.stdout
    assert ".tours/x.tour" in res.stdout


# --------------------------------------------------------------------------- #
# loop --tdd / --team / --logic  and  research --web flags
# --------------------------------------------------------------------------- #
def test_parser_loop_tdd_team_logic_flags():
    a = build_parser().parse_args(["loop", "--topic", "d", "--execute", "--tdd", "--team", "--logic"])
    assert a.tdd is True and a.team is True and a.logic is True
    # tdd/team stay opt-in; logic defaults ON (--no-logic opts out).
    b = build_parser().parse_args(["loop", "--topic", "d"])
    assert b.tdd is False and b.team is False and b.logic is True
    c = build_parser().parse_args(["loop", "--topic", "d", "--no-logic"])
    assert c.logic is False


def test_parser_loop_all_flag():
    a = build_parser().parse_args(["loop", "--topic", "d", "--all"])
    assert a.all is True
    # --all itself doesn't force tdd/team True at parse time (cmd_loop applies
    # the flip); the parser default for tdd/team stays False until cmd_loop runs.
    b = build_parser().parse_args(["loop", "--topic", "d"])
    assert b.all is False


def test_parser_learn_force_flag():
    a = build_parser().parse_args(["learn", "--force"])
    assert a.force is True
    b = build_parser().parse_args(["learn"])
    assert b.force is False


def test_parser_setup_repo_flags():
    a = build_parser().parse_args(["setup-repo", "--domains", "nlp,rl", "--no-learn"])
    assert a.domains == "nlp,rl" and a.no_learn is True
    b = build_parser().parse_args(["setup-repo"])
    assert b.domains is None and b.no_learn is False


def test_parser_uninstall_flag():
    a = build_parser().parse_args(["uninstall", "--yes"])
    assert a.yes is True
    b = build_parser().parse_args(["uninstall"])
    assert b.yes is False


def test_parser_loop_simplify_flag():
    a = build_parser().parse_args(["loop", "--topic", "d", "--execute", "--simplify"])
    assert a.simplify is True
    # simplify defaults ON; --no-simplify opts out.
    b = build_parser().parse_args(["loop", "--topic", "d"])
    assert b.simplify is True
    c = build_parser().parse_args(["loop", "--topic", "d", "--no-simplify"])
    assert c.simplify is False


def test_parser_loop_e2e_flag_defaults_on():
    a = build_parser().parse_args(["loop", "--topic", "d"])
    assert a.e2e is True
    b = build_parser().parse_args(["loop", "--topic", "d", "--no-e2e"])
    assert b.e2e is False


def test_cmd_loop_all_flag_applies_flip(tmp_path, monkeypatch, capsys):
    """--all is applied inside cmd_loop (tdd/team default False at parse time,
    but must flip True once cmd_loop runs) — an in-process check with run_loop
    monkeypatched so no real agent is ever invoked (cmd_loop has no direct
    unit test elsewhere; this stays in-process instead of a subprocess so a
    `claude` CLI present on the test machine can never make it hang)."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify

    (tmp_path / ".git").mkdir()  # project_root() walks up looking for .git
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    captured = {}

    def fake_run_loop(tasks, ws, skills_dir, max_cycles, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--all"])
    main_mod.cmd_loop(args)

    out = capsys.readouterr().out
    assert "every axis on" in out
    assert captured["make_test_writer"] is not None  # tdd
    assert captured["team"] is True
    assert captured["make_logic_checker"] is not None
    assert captured["make_simplifier"] is not None
    assert captured["make_advisor"] is not None
    assert captured["make_e2e_runner"] is not None


def test_codex_tdd_without_tdd_is_usage_error(tmp_path, monkeypatch, capsys):
    """--codex-tdd requires --tdd; without it, cmd_loop errors before running anything."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    def fake_run_loop(*a, **k):
        raise AssertionError("run_loop must not be called when --codex-tdd validation fails")

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--codex-tdd"])
    result = main_mod.cmd_loop(args)

    assert result == 1
    out = capsys.readouterr().out
    assert "--codex-tdd requires --tdd" in out


def test_codex_tdd_with_all_flag_is_not_rejected(tmp_path, monkeypatch, capsys):
    """--all implies --tdd, so --all --codex-tdd together must NOT be rejected
    by the --codex-tdd/--tdd validation guard (regression for a validation-
    ordering bug: the guard used to run before the --all flip applied)."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    captured = {}

    def fake_run_loop(tasks, ws, skills_dir, max_cycles, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(
        ["loop", "--topic", "demo", "--execute", "--all", "--codex-tdd"]
    )
    main_mod.cmd_loop(args)

    assert "make_test_writer" in captured
    assert captured["make_test_writer"] is not None


def test_codex_flags_default_false():
    args = build_parser().parse_args(["loop", "--topic", "t", "--execute"])
    assert args.codex_verify is False
    assert args.codex_tdd is False


def test_codex_verify_flag_parses():
    args = build_parser().parse_args(["loop", "--topic", "t", "--execute", "--codex-verify"])
    assert args.codex_verify is True


def test_codex_verify_wires_codex_backed_verifier(tmp_path, monkeypatch, capsys):
    """--codex-verify swaps make_verifier to a codex-backed factory; implementer untouched."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify
    from cli.runner import AgentRunner

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    captured = {}

    def fake_run_loop(tasks, ws, skills_dir, max_cycles, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--codex-verify"])
    main_mod.cmd_loop(args)

    verifier = captured["make_verifier"]()
    assert isinstance(verifier, AgentRunner)
    assert verifier.executable == "codex"
    assert verifier.argv_builder is not None
    assert verifier.output_cleaner is not None

    implementer = captured["make_implementer"]()
    assert implementer.executable == "claude"


def test_parser_research_web_flag():
    a = build_parser().parse_args(["research", "topic", "--web"])
    assert a.web is True
    b = build_parser().parse_args(["research", "topic", "--deep"])
    assert b.deep is True and b.web is False


# --------------------------------------------------------------------------- #
# cmd_research wiring — real synthesis must actually fire on the CLI path
# --------------------------------------------------------------------------- #
def test_cmd_research_passes_a_synthesis_runner(tmp_path, monkeypatch):
    """The whole point of the real-synthesis feature is dead unless cmd_research
    actually passes a synthesis_runner into research(). Capture the kwargs
    cmd_research calls research(...) with and assert it's wired, not None.
    """
    import cli.main as main_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sigma.config.yml").write_text("name: t\ndomains: [nlp]\nmodels: [claude]\n")

    captured = {}

    def fake_research(topic, models, ws, **kwargs):
        captured.update(kwargs)
        captured["topic"] = topic
        out = ws / "research.md"
        ws.mkdir(parents=True, exist_ok=True)
        out.write_text("# stub\n")
        return out

    monkeypatch.setattr(main_mod, "research", fake_research)

    ns = argparse.Namespace(topic="wiring check", models=None, deep=False, web=False)
    rc = main_mod.cmd_research(ns)
    assert rc == 0
    assert captured.get("synthesis_runner") is not None


# --------------------------------------------------------------------------- #
# cmd_hermes wiring — per-stage model routing (+ --no-route opt-out)
# --------------------------------------------------------------------------- #
def test_cmd_hermes_routes_stages_by_default(monkeypatch, tmp_path):
    captured = {}

    def fake_run_hermes(message, ws, **kwargs):
        captured.update(kwargs)
        from cli.hermes import HermesResult
        return HermesResult(ok=True)

    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.hermes.run_hermes", fake_run_hermes)
    from cli.main import main
    assert main(["hermes", "continue", "--topic", "t"]) == 0
    routes = captured["stage_routes"]
    assert routes["spec"] == "opus"
    assert routes["implement-task"] == "sonnet"


def test_cmd_hermes_no_route_passes_empty_routes(monkeypatch, tmp_path):
    captured = {}

    def fake_run_hermes(message, ws, **kwargs):
        captured.update(kwargs)
        from cli.hermes import HermesResult
        return HermesResult(ok=True)

    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.hermes.run_hermes", fake_run_hermes)
    from cli.main import main
    assert main(["hermes", "continue", "--topic", "t", "--no-route"]) == 0
    assert captured["stage_routes"] == {}
