import argparse

from cli.main import cmd_usage, main
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


# --------------------------------------------------------------------------- #
# Regression: argparse REMAINDER swallows a leading flag (Finding 1).
#
# `sigma usage --json` used to hit a well-known argparse limitation: when the
# FIRST passthrough token starts with `-`/`--`, argparse's own optional-arg
# matching intercepts it before REMAINDER can capture it, raising
# SystemExit(2) instead of forwarding to ccusage. main() now intercepts raw
# argv for "usage" before parse_args runs, so this must reach _usage_spawn
# with the flag intact.
# --------------------------------------------------------------------------- #
def test_main_usage_forwards_leading_flag_verbatim(monkeypatch):
    calls = []

    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: calls.append(argv) or 0)

    rc = main(["usage", "--json"])

    assert rc == 0
    assert calls == [["npx", "-y", "ccusage@latest", "--json"]]


def test_main_usage_forwards_leading_flag_with_value_verbatim(monkeypatch):
    calls = []

    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: calls.append(argv) or 0)

    rc = main(["usage", "--since", "7daysAgo"])

    assert rc == 0
    assert calls == [["npx", "-y", "ccusage@latest", "--since", "7daysAgo"]]


def test_main_usage_still_forwards_plain_positional_first_token(monkeypatch):
    calls = []

    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: calls.append(argv) or 0)

    rc = main(["usage", "claude", "session"])

    assert rc == 0
    assert calls == [["npx", "-y", "ccusage@latest", "claude", "session"]]
