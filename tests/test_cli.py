import argparse
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
# loop --tdd / --team / --logic  and  research --web flags
# --------------------------------------------------------------------------- #
def test_parser_loop_tdd_team_logic_flags():
    a = build_parser().parse_args(["loop", "--topic", "d", "--execute", "--tdd", "--team", "--logic"])
    assert a.tdd is True and a.team is True and a.logic is True
    b = build_parser().parse_args(["loop", "--topic", "d"])
    assert b.tdd is False and b.team is False and b.logic is False


def test_parser_research_web_flag():
    a = build_parser().parse_args(["research", "topic", "--web"])
    assert a.web is True
    b = build_parser().parse_args(["research", "topic", "--deep"])
    assert b.deep is True and b.web is False
