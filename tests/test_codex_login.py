"""Tests for cli.codex_login — detect/prompt ChatGPT sign-in for the codex CLI.

All process spawning and PATH lookups are injected, so no real login flow runs.
"""

from __future__ import annotations

from cli import codex_login


def _which(present):
    return lambda name: f"/usr/bin/{name}" if name in present else None


# --------------------------- status --------------------------- #
def test_status_not_installed():
    st = codex_login.codex_login_status(which=_which(set()))
    assert st["installed"] is False
    assert st["logged_in"] is False


def test_status_installed_logged_in():
    st = codex_login.codex_login_status(
        which=_which({"codex"}),
        run=lambda argv: (0, "Logged in using ChatGPT"),
    )
    assert st["installed"] is True
    assert st["logged_in"] is True


def test_status_installed_not_logged_in():
    st = codex_login.codex_login_status(
        which=_which({"codex"}),
        run=lambda argv: (1, "Not logged in"),
    )
    assert st["installed"] is True
    assert st["logged_in"] is False


def test_status_installed_unexpected_output_defaults_not_logged_in():
    """A zero exit with unrecognized text is treated as not logged in (safe default)."""
    st = codex_login.codex_login_status(
        which=_which({"codex"}),
        run=lambda argv: (0, "some future CLI message we don't recognize"),
    )
    assert st["logged_in"] is False


# --------------------------- setup (confirm-gated orchestration) --------------------------- #
def test_setup_noop_when_not_installed():
    spawned = []
    changed = codex_login.setup_codex_login(
        status_fn=lambda: {"installed": False, "logged_in": False},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == []
    assert changed is False


def test_setup_noop_when_already_logged_in():
    spawned = []
    changed = codex_login.setup_codex_login(
        status_fn=lambda: {"installed": True, "logged_in": True},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == []
    assert changed is False


def test_setup_skips_when_user_declines():
    spawned = []
    changed = codex_login.setup_codex_login(
        status_fn=lambda: {"installed": True, "logged_in": False},
        confirm=lambda msg: False,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == []
    assert changed is False


def test_setup_spawns_login_on_confirm():
    spawned = []
    changed = codex_login.setup_codex_login(
        status_fn=lambda: {"installed": True, "logged_in": False},
        confirm=lambda msg: True,
        spawn=lambda argv: spawned.append(argv) or 0,
    )
    assert spawned == [["codex", "login"]]
    assert changed is True


def test_setup_reports_failure_when_spawn_fails():
    changed = codex_login.setup_codex_login(
        status_fn=lambda: {"installed": True, "logged_in": False},
        confirm=lambda msg: True,
        spawn=lambda argv: 1,
    )
    assert changed is False
