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


def test_stage_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("spec", "--topic", "demo", "--dry-run")
    # dry-run prints the invocation and exits 0 (no claude needed)
    assert res.returncode == 0
    assert "spec" in res.stdout


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


def test_board_missing_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = run_cli("board", "--topic", "nope")
    assert res.returncode == 1
    assert "no spec workspace" in res.stdout
