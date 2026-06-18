"""Tests for cli.rtk — detect/install/activate the RTK token-saver.

All process spawning and PATH/settings lookups are injected, so no real install
runs and the global ~/.claude/settings.json is never touched.
"""

from __future__ import annotations

import json

from cli import rtk


def _which(present):
    return lambda name: f"/usr/bin/{name}" if name in present else None


# --------------------------- status --------------------------- #
def test_status_not_installed():
    st = rtk.rtk_status(which=_which(set()))
    assert st["installed"] is False
    assert st["hook_active"] is False


def test_status_installed_gain_ok(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"command": "rtk"}]}}))
    st = rtk.rtk_status(
        which=_which({"rtk"}),
        run=lambda argv: (0, "rtk 1.2.3"),
        settings_path=settings,
    )
    assert st["installed"] is True
    assert st["gain_ok"] is True
    assert st["hook_active"] is True


def test_status_gain_fails_name_collision(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    st = rtk.rtk_status(
        which=_which({"rtk"}),
        run=lambda argv: (1, "error: unknown command 'gain'"),
        settings_path=settings,
    )
    assert st["installed"] is True
    assert st["gain_ok"] is False


def test_status_hook_inactive_when_settings_missing_rtk(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"command": "other"}]}}))
    st = rtk.rtk_status(
        which=_which({"rtk"}),
        run=lambda argv: (0, "rtk 1.0"),
        settings_path=settings,
    )
    assert st["hook_active"] is False


def test_status_handles_absent_settings_file(tmp_path):
    st = rtk.rtk_status(
        which=_which({"rtk"}),
        run=lambda argv: (0, "rtk 1.0"),
        settings_path=tmp_path / "nope.json",
    )
    assert st["installed"] is True
    assert st["hook_active"] is False


# --------------------------- install --------------------------- #
def test_install_prefers_brew_when_present():
    spawned = []
    rtk.install_rtk(
        which=_which({"brew"}),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned
    assert spawned[0][0] == "brew"


def test_install_falls_back_to_curl_without_brew():
    spawned = []
    rtk.install_rtk(
        which=_which(set()),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned
    joined = " ".join(spawned[0])
    assert "curl" in joined or "sh" in joined


# --------------------------- activate --------------------------- #
def test_activate_runs_init_global():
    spawned = []
    rc = rtk.activate_rtk(spawn=lambda argv: spawned.append(argv) or 0)
    assert spawned == [["rtk", "init", "-g"]]
    assert rc is True


def test_activate_reports_failure():
    rc = rtk.activate_rtk(spawn=lambda argv: 1)
    assert rc is False


# --------------------------- setup (confirm-gated orchestration) --------------------------- #
def test_setup_skips_when_user_declines():
    spawned = []
    rtk.setup_rtk(
        status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        confirm=lambda msg: False,  # user says no
        which=_which(set()),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == []  # nothing installed without consent


def test_setup_installs_and_activates_on_confirm():
    spawned = []
    rtk.setup_rtk(
        status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        confirm=lambda msg: True,
        which=_which({"brew"}),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    cmds = [a[0] for a in spawned]
    assert "brew" in cmds  # installed
    assert ["rtk", "init", "-g"] in spawned  # activated


def test_setup_only_activates_when_installed_not_active():
    spawned = []
    rtk.setup_rtk(
        status_fn=lambda: {"installed": True, "hook_active": False, "gain_ok": True},
        confirm=lambda msg: True,
        which=_which({"rtk"}),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    # no brew/curl install, just activation
    assert ["rtk", "init", "-g"] in spawned
    assert all(a[0] != "brew" for a in spawned)


def test_setup_noop_when_fully_active():
    spawned = []
    changed = rtk.setup_rtk(
        status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        confirm=lambda msg: True,
        which=_which({"rtk"}),
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == []
    assert changed is False
