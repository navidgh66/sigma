"""Tests for cli.session_hook — confirm-gated install of the SessionStart hook.

The hook runs `sigma session-context` at session start; its stdout is injected as
additionalContext, surfacing the learn pointer. It is written into the PROJECT
.claude/settings.json (repo-scoped) via an immutable merge that preserves every
other key — mirrors cli/statusline.py exactly.
"""

from __future__ import annotations

import json

from cli import session_hook as sh


# --------------------------- status detection --------------------------- #
def test_status_configured(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(sh.install_payload({})))
    assert sh.session_hook_status(settings_path=settings) == {"configured": True}


def test_status_not_configured_when_absent(tmp_path):
    assert sh.session_hook_status(settings_path=tmp_path / "none.json") == {"configured": False}


def test_status_other_hooks_dont_count(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": "echo unrelated"}]}
    ]}}))
    assert sh.session_hook_status(settings_path=settings) == {"configured": False}


def test_status_tolerates_bad_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ not json")
    assert sh.session_hook_status(settings_path=settings) == {"configured": False}


# --------------------------- install (preserves other keys) --------------------------- #
def test_install_preserves_existing_settings(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "opus", "hooks": {"Stop": ["x"]}}))
    ok = sh.install_session_hook(settings_path=settings)
    assert ok is True
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"                 # preserved
    assert data["hooks"]["Stop"] == ["x"]          # other hooks preserved
    # our SessionStart entry runs sigma session-context
    cmds = [
        h["command"]
        for entry in data["hooks"]["SessionStart"]
        for h in entry.get("hooks", [])
    ]
    assert any("session-context" in c for c in cmds)


def test_install_creates_settings_when_absent(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    ok = sh.install_session_hook(settings_path=settings)
    assert ok is True
    assert sh.session_hook_status(settings_path=settings) == {"configured": True}


def test_install_does_not_mutate_loaded_dict(tmp_path):
    settings = tmp_path / "settings.json"
    original = {"hooks": {"SessionStart": []}}
    settings.write_text(json.dumps(original))
    sh.install_session_hook(settings_path=settings)
    # the literal we passed in stays untouched (immutable merge)
    assert original == {"hooks": {"SessionStart": []}}


# --------------------------- setup (confirm-gated) --------------------------- #
def test_setup_noop_when_already_configured():
    changed = sh.setup_session_hook(
        status_fn=lambda: {"configured": True},
        confirm=lambda msg: True,
    )
    assert changed is False


def test_setup_skipped_when_declined():
    written = []
    changed = sh.setup_session_hook(
        status_fn=lambda: {"configured": False},
        confirm=lambda msg: False,
        writer=lambda p, d: written.append(d) or True,
    )
    assert changed is False
    assert written == []


def test_setup_installs_on_confirm(tmp_path):
    written = []
    changed = sh.setup_session_hook(
        status_fn=lambda: {"configured": False},
        confirm=lambda msg: True,
        settings_path=tmp_path / "settings.json",
        writer=lambda p, d: written.append(d) or True,
    )
    assert changed is True
    assert written and "hooks" in written[0]
