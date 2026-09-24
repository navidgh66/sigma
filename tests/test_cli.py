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
    # The in-session /loop replaced the CLI engine: these are gone too.
    for gone in ("loop", "hermes", "board", "weave"):
        assert gone not in commands, f"{gone} must not be a CLI subcommand"
    # The kept commands remain.
    assert {"research", "learn", "review", "profile", "doctor"} <= commands


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

    ns = argparse.Namespace(topic="wiring check", models=None, deep=False, web=False, no_route=False)
    rc = main_mod.cmd_research(ns)
    assert rc == 0
    assert captured.get("synthesis_runner") is not None


# --------------------------------------------------------------------------- #
# cmd_hermes wiring — per-stage model routing (+ --no-route opt-out)
# --------------------------------------------------------------------------- #
def test_cmd_research_routes_synthesis_to_strong_tier(monkeypatch, tmp_path):
    captured = {}

    def fake_research(topic, models, ws, requested_tools=None, deep=False, web=False, synthesis_runner=None):
        captured["runner"] = synthesis_runner
        out = tmp_path / "research.md"
        out.write_text("x")
        return out

    calls = {}

    def fake_run_model(model, prompt, model_alias=None, **kwargs):
        calls["alias"] = model_alias
        from cli.models import ModelResult
        return ModelResult(model=model, ok=True, text="s")

    monkeypatch.setattr("cli.main.research", fake_research)
    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.research.run_model", fake_run_model)
    from cli.main import main
    assert main(["research", "some topic"]) == 0
    captured["runner"]("prompt")
    assert calls["alias"] == "opus"


def test_cmd_research_no_route_uses_default_synthesis(monkeypatch, tmp_path):
    captured = {}

    def fake_research(topic, models, ws, requested_tools=None, deep=False, web=False, synthesis_runner=None):
        captured["runner"] = synthesis_runner
        out = tmp_path / "research.md"
        out.write_text("x")
        return out

    monkeypatch.setattr("cli.main.research", fake_research)
    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    from cli.main import main
    from cli.research import claude_synthesis_runner
    assert main(["research", "some topic", "--no-route"]) == 0
    assert captured["runner"] is claude_synthesis_runner


# --------------------------------------------------------------------------- #
# cmd_loop telemetry — real measured tokens recorded into the cost ledger
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# eval --from-spec — spec→eval autogeneration
# --------------------------------------------------------------------------- #
def _spec_ws(tmp_path, monkeypatch, spec_text):
    import cli.main as main_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sigma.config.yml").write_text("name: t\ndomains: [nlp]\nmodels: [claude]\n")
    ws = tmp_path / "sigma" / "specs" / "2026-01-01-demo"
    ws.mkdir(parents=True)
    if spec_text is not None:
        (ws / "spec.md").write_text(spec_text)
    monkeypatch.setattr(main_mod, "spec_workspace", lambda topic: ws)
    return ws


SPEC_WITH_SCENARIOS = """# Spec
Scenario: happy path
Given a fresh db
When the flow runs
Then a row exists
"""


def test_eval_from_spec_generates_set(monkeypatch, tmp_path):
    from cli.main import main

    _spec_ws(tmp_path, monkeypatch, SPEC_WITH_SCENARIOS)
    assert main(["eval", "--from-spec", "demo"]) == 0
    out = tmp_path / "sigma" / "evals" / "2026-01-01-demo.md"
    assert out.exists()
    assert "## case: happy-path" in out.read_text()


def test_eval_from_spec_refuses_overwrite_without_force(monkeypatch, tmp_path):
    from cli.main import main

    _spec_ws(tmp_path, monkeypatch, SPEC_WITH_SCENARIOS)
    assert main(["eval", "--from-spec", "demo"]) == 0
    assert main(["eval", "--from-spec", "demo"]) == 1
    assert main(["eval", "--from-spec", "demo", "--force"]) == 0


def test_eval_from_spec_errors_without_spec(monkeypatch, tmp_path):
    from cli.main import main

    _spec_ws(tmp_path, monkeypatch, None)
    assert main(["eval", "--from-spec", "demo"]) == 1


def test_eval_requires_set_or_from_spec(monkeypatch, tmp_path):
    from cli.main import main

    _spec_ws(tmp_path, monkeypatch, SPEC_WITH_SCENARIOS)
    assert main(["eval"]) == 1
