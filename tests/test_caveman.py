"""Tests for cli.caveman — detect/install the caveman mode (all I/O injected)."""

from __future__ import annotations

import json

from cli import caveman


def _write_settings(path, hooks):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}))


def _write_plugins(path, plugins):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"plugins": plugins}))


# --------------------------- status detection --------------------------- #
def test_status_all_present(tmp_path):
    settings = tmp_path / "settings.json"
    plugins = tmp_path / "installed_plugins.json"
    _write_settings(settings, {"SessionStart": [{"hooks": [{"command": "node caveman-activate.js"}]}]})
    _write_plugins(plugins, {"caveman@caveman": [{"scope": "user"}]})

    st = caveman.caveman_status(
        which=lambda n: "/usr/bin/claude" if n == "claude" else None,
        settings_path=settings,
        plugins_path=plugins,
    )
    assert st == {"claude_cli": True, "installed": True, "hook_active": True}


def test_status_nothing_present(tmp_path):
    st = caveman.caveman_status(
        which=lambda n: None,
        settings_path=tmp_path / "missing.json",
        plugins_path=tmp_path / "missing-plugins.json",
    )
    assert st == {"claude_cli": False, "installed": False, "hook_active": False}


def test_status_hook_inactive_but_installed(tmp_path):
    settings = tmp_path / "settings.json"
    plugins = tmp_path / "installed_plugins.json"
    _write_settings(settings, {"SessionStart": [{"hooks": [{"command": "node other.js"}]}]})
    _write_plugins(plugins, {"caveman@caveman": [{"scope": "user"}]})

    st = caveman.caveman_status(
        which=lambda n: "/usr/bin/claude",
        settings_path=settings,
        plugins_path=plugins,
    )
    assert st["installed"] is True
    assert st["hook_active"] is False


def test_status_tolerates_bad_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ not json")
    st = caveman.caveman_status(
        which=lambda n: None,
        settings_path=settings,
        plugins_path=tmp_path / "nope.json",
    )
    assert st["hook_active"] is False


# --------------------------- setup (confirm-gated) --------------------------- #
def test_setup_noop_when_already_active():
    spawned = []
    changed = caveman.setup_caveman(
        status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is False
    assert spawned == []  # nothing installed


def test_setup_noop_without_claude_cli():
    spawned = []
    changed = caveman.setup_caveman(
        status_fn=lambda: {"claude_cli": False, "installed": False, "hook_active": False},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is False
    assert spawned == []


def test_setup_skipped_when_declined():
    spawned = []
    changed = caveman.setup_caveman(
        status_fn=lambda: {"claude_cli": True, "installed": False, "hook_active": False},
        confirm=lambda msg: False,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is False
    assert spawned == []


def test_setup_installs_on_confirm():
    spawned = []
    changed = caveman.setup_caveman(
        status_fn=lambda: {"claude_cli": True, "installed": False, "hook_active": False},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert changed is True
    # Both marketplace-add and plugin-install ran.
    assert any("marketplace" in a for a in spawned)
    assert any("install" in a for a in spawned)


def test_setup_reports_failure_when_spawn_fails():
    changed = caveman.setup_caveman(
        status_fn=lambda: {"claude_cli": True, "installed": False, "hook_active": False},
        confirm=lambda msg: True,
        spawn=lambda argv: 1,  # install fails
    )
    assert changed is False
