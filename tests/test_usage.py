import argparse

from cli.main import cmd_usage
from cli.usage import MISSING_NODE_MESSAGE, build_argv, node_runtime_available


def test_node_runtime_available_true_when_npx_on_path():
    def fake_which(exe):
        return "/usr/bin/npx" if exe == "npx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_true_when_only_bunx_on_path():
    def fake_which(exe):
        return "/usr/bin/bunx" if exe == "bunx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_false_when_neither_present():
    assert node_runtime_available(which=lambda exe: None) is False


def test_build_argv_prepends_npx_ccusage():
    argv = build_argv([])
    assert argv == ["npx", "-y", "ccusage@latest"]


def test_build_argv_appends_passthrough_args_unmodified():
    argv = build_argv(["claude", "session", "--json"])
    assert argv == ["npx", "-y", "ccusage@latest", "claude", "session", "--json"]


def test_missing_node_message_mentions_npx_and_ccusage():
    assert "npx" in MISSING_NODE_MESSAGE.lower()
    assert "ccusage" in MISSING_NODE_MESSAGE.lower()


def test_cmd_usage_calls_spawn_with_built_argv(monkeypatch):
    calls = []

    def fake_which(exe):
        return "/usr/bin/npx" if exe == "npx" else None

    def fake_spawn(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr("cli.usage.shutil.which", fake_which)
    monkeypatch.setattr("cli.main._usage_spawn", fake_spawn)

    args = argparse.Namespace(usage_args=["claude", "session"])
    rc = cmd_usage(args)

    assert rc == 0
    assert calls == [["npx", "-y", "ccusage@latest", "claude", "session"]]


def test_cmd_usage_returns_0_and_skips_spawn_when_node_missing(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: calls.append(argv))

    args = argparse.Namespace(usage_args=[])
    rc = cmd_usage(args)

    assert rc == 0
    assert calls == []  # spawn never called
    captured = capsys.readouterr()
    assert "npx" in captured.out.lower()


def test_cmd_usage_passes_through_exit_code(monkeypatch):
    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: 7)

    args = argparse.Namespace(usage_args=[])
    rc = cmd_usage(args)

    assert rc == 7
