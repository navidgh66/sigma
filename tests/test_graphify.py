"""Tests for cli.graphify — detect, install, build-argv, and report injection.

Mirrors test_rtk / test_caveman: every lookup and spawn is injected, so tests
never install anything, spawn a real process, or hit the network.
"""

from __future__ import annotations

from pathlib import Path

from cli.graphify import (
    build_extract_argv,
    graphify_hook_status,
    graphify_status,
    install_graphify,
    report_block,
    setup_graphify,
)


# --------------------------- status --------------------------- #
def test_status_installed_when_on_path():
    st = graphify_status(which=lambda exe: "/usr/bin/graphify")
    assert st["installed"] is True


def test_status_absent_when_not_on_path():
    st = graphify_status(which=lambda exe: None)
    assert st["installed"] is False


# --------------------------- install fallback order --------------------------- #
def test_install_prefers_uv():
    calls = []

    def spawn(argv):
        calls.append(argv)
        return 0  # uv succeeds first

    ok = install_graphify(which=lambda exe: "/bin/uv" if exe == "uv" else None, spawn=spawn)
    assert ok is True
    assert calls[0][0] == "uv"
    assert calls[0][1:3] == ["tool", "install"]
    assert len(calls) == 1  # stops after first success


def test_install_falls_back_to_pipx_when_no_uv():
    calls = []

    def spawn(argv):
        calls.append(argv)
        return 0

    ok = install_graphify(
        which=lambda exe: "/bin/pipx" if exe == "pipx" else None, spawn=spawn
    )
    assert ok is True
    assert calls[0][0] == "pipx"


def test_install_falls_back_to_pip_when_neither():
    calls = []

    def spawn(argv):
        calls.append(argv)
        return 0

    ok = install_graphify(which=lambda exe: None, spawn=spawn)
    assert ok is True
    # pip path runs python -m pip install --user graphifyy
    assert "pip" in calls[0]
    assert "graphifyy" in calls[0]


def test_install_returns_false_when_spawn_fails():
    ok = install_graphify(which=lambda exe: "/bin/uv", spawn=lambda argv: 1)
    assert ok is False


# --------------------------- setup (confirm-gated, idempotent) --------------------------- #
def test_setup_noop_when_already_installed():
    spawned = []
    changed = setup_graphify(
        status_fn=lambda: {"installed": True},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is False
    assert spawned == []  # never touched anything


def test_setup_noop_when_declined():
    spawned = []
    changed = setup_graphify(
        status_fn=lambda: {"installed": False},
        confirm=lambda msg: False,
        which=lambda exe: "/bin/uv",
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is False
    assert spawned == []


def test_setup_installs_when_absent_and_confirmed():
    spawned = []
    changed = setup_graphify(
        status_fn=lambda: {"installed": False},
        confirm=lambda msg: True,
        which=lambda exe: "/bin/uv",
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is True
    assert spawned and spawned[0][0] == "uv"


# --------------------------- extract argv --------------------------- #
def test_build_extract_argv_is_incremental(tmp_path):
    argv = build_extract_argv(tmp_path)
    assert argv[:2] == ["graphify", "extract"]
    assert "--update" in argv  # incremental re-extraction


# --------------------------- report block injection --------------------------- #
def test_report_block_empty_when_absent(tmp_path):
    assert report_block(tmp_path) == ""


def test_report_block_reads_graph_report(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("# Graph\nGod node: main.py")
    block = report_block(tmp_path)
    assert "God node: main.py" in block
    # It must be labeled so the agent knows what it is.
    assert "graph" in block.lower()


def test_report_block_caps_oversized(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("x" * 10_000)
    block = report_block(tmp_path, cap=500)
    # Capped well below the raw size (block adds a small header + truncation notice).
    assert len(block) < 1200
    assert "truncat" in block.lower()


def test_report_block_unreadable_dir_is_safe(tmp_path):
    # graphify-out exists as a FILE, not a dir → reading the report path fails → "".
    (tmp_path / "graphify-out").write_text("not a dir")
    assert report_block(tmp_path) == ""


# --------------------------- hook status --------------------------- #
def _make_repo(tmp_path: Path, hook_body: str = None) -> Path:
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    if hook_body is not None:
        (hooks / "post-commit").write_text(hook_body)
    return tmp_path


def test_hook_status_installed_when_marker_present(tmp_path):
    root = _make_repo(tmp_path, "#!/bin/sh\nexec /path/to/graphify update .\n")
    assert graphify_hook_status(root)["installed"] is True


def test_hook_status_absent_when_no_hook_file(tmp_path):
    root = _make_repo(tmp_path, hook_body=None)
    assert graphify_hook_status(root)["installed"] is False


def test_hook_status_absent_when_hook_lacks_marker(tmp_path):
    root = _make_repo(tmp_path, "#!/bin/sh\necho hello\n")
    assert graphify_hook_status(root)["installed"] is False


def test_hook_status_absent_when_no_git_dir(tmp_path):
    assert graphify_hook_status(tmp_path)["installed"] is False
