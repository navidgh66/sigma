"""Tests for cli.statusline — detect/configure ccstatusline (all I/O injected)."""

from __future__ import annotations

import json

from cli import statusline


# --------------------------- status detection --------------------------- #
def test_status_configured(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "npx -y ccstatusline@latest"}}))
    st = statusline.statusline_status(
        which=lambda n: "/usr/bin/npx" if n == "npx" else None,
        settings_path=settings,
    )
    assert st == {"node_runtime": True, "configured": True}


def test_status_nothing_present(tmp_path):
    st = statusline.statusline_status(
        which=lambda n: None,
        settings_path=tmp_path / "missing.json",
    )
    assert st == {"node_runtime": False, "configured": False}


def test_status_bunx_counts_as_runtime(tmp_path):
    st = statusline.statusline_status(
        which=lambda n: "/usr/bin/bunx" if n == "bunx" else None,
        settings_path=tmp_path / "missing.json",
    )
    assert st["node_runtime"] is True


def test_status_empty_statusline_not_configured(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"statusLine": {"type": "command"}}))  # no command
    st = statusline.statusline_status(which=lambda n: None, settings_path=settings)
    assert st["configured"] is False


def test_status_tolerates_bad_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{ not json")
    st = statusline.statusline_status(which=lambda n: None, settings_path=settings)
    assert st["configured"] is False


# --------------------------- install (preserves other keys) --------------------------- #
def test_install_preserves_existing_settings(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"SessionStart": []}, "model": "opus"}))
    ok = statusline.install_statusline(settings_path=settings)
    assert ok is True
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"          # preserved
    assert data["hooks"] == {"SessionStart": []}  # preserved
    assert data["statusLine"]["command"] == "npx -y ccstatusline@latest"


def test_install_creates_settings_when_absent(tmp_path):
    settings = tmp_path / "nested" / "settings.json"
    ok = statusline.install_statusline(settings_path=settings)
    assert ok is True
    assert json.loads(settings.read_text())["statusLine"]["command"]


# --------------------------- setup (confirm-gated) --------------------------- #
def test_setup_noop_when_already_configured():
    changed = statusline.setup_statusline(
        status_fn=lambda: {"node_runtime": True, "configured": True},
        confirm=lambda msg: True,
    )
    assert changed is False


def test_setup_noop_without_node_runtime():
    changed = statusline.setup_statusline(
        status_fn=lambda: {"node_runtime": False, "configured": False},
        confirm=lambda msg: True,
    )
    assert changed is False


def test_setup_skipped_when_declined():
    written = []
    changed = statusline.setup_statusline(
        status_fn=lambda: {"node_runtime": True, "configured": False},
        confirm=lambda msg: False,
        writer=lambda p, d: written.append(d) or True,
    )
    assert changed is False
    assert written == []


def test_setup_installs_on_confirm(tmp_path):
    written = []
    changed = statusline.setup_statusline(
        status_fn=lambda: {"node_runtime": True, "configured": False},
        confirm=lambda msg: True,
        settings_path=tmp_path / "settings.json",
        writer=lambda p, d: written.append(d) or True,
    )
    assert changed is True
    assert written and written[0]["statusLine"]["command"] == "npx -y ccstatusline@latest"
