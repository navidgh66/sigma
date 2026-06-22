"""Tests for cli.doctor — diagnose, confirm-gated fixes, exit codes."""

from __future__ import annotations

from cli import doctor
from cli.checks import FAIL, OK, WARN, Check


def _checks(*specs):
    """specs: (name, status, fixable) tuples → Check list with recording fixes."""
    applied = []
    out = []
    for name, status, fixable in specs:
        fix = None
        if fixable:
            fix = (f"fix {name}", (lambda n=name: applied.append(n) or True))
        out.append(Check(name, status, "detail", fix=fix))
    return out, applied


def test_all_ok_exit_zero():
    checks, _ = _checks(("python", OK, False), ("deps", OK, False))
    rc = doctor.run_doctor(check_only=True, run_all=lambda **k: checks, use_rich=False)
    assert rc == 0


def test_fail_exit_one_in_check_mode():
    checks, _ = _checks(("deps", FAIL, True))
    rc = doctor.run_doctor(check_only=True, run_all=lambda **k: checks, use_rich=False)
    assert rc == 1


def test_check_mode_never_applies_fixes():
    checks, applied = _checks(("deps", FAIL, True))
    doctor.run_doctor(check_only=True, run_all=lambda **k: checks, use_rich=False)
    assert applied == []  # read-only


def test_confirm_yes_applies_fix():
    checks, applied = _checks(("deps", FAIL, True))
    doctor.run_doctor(
        run_all=lambda **k: checks, confirm=lambda msg: True, use_rich=False
    )
    assert applied == ["deps"]


def test_confirm_no_skips_fix():
    checks, applied = _checks(("deps", FAIL, True))
    doctor.run_doctor(
        run_all=lambda **k: checks, confirm=lambda msg: False, use_rich=False
    )
    assert applied == []


def test_auto_yes_applies_without_prompt():
    checks, applied = _checks(("deps", FAIL, True), ("rtk", WARN, True))
    confirm_calls = []
    doctor.run_doctor(
        run_all=lambda **k: checks,
        auto_yes=True,
        confirm=lambda msg: confirm_calls.append(msg) or False,
        use_rich=False,
    )
    assert applied == ["deps", "rtk"]
    assert confirm_calls == []  # --yes skips prompts


def test_warn_only_exits_zero():
    checks, _ = _checks(("rtk", WARN, True))
    rc = doctor.run_doctor(check_only=True, run_all=lambda **k: checks, use_rich=False)
    assert rc == 0  # warnings don't fail the gate


def test_update_invokes_updater():
    checks, _ = _checks(("python", OK, False))
    called = []
    doctor.run_doctor(
        update=True,
        run_all=lambda **k: checks,
        updater=lambda: called.append("updated"),
        use_rich=False,
    )
    assert called == ["updated"]


def test_default_updater_updates_plugin_when_claude_present():
    # When `claude` is on PATH, the updater refreshes the marketplace AND the
    # plugin (the CLI git pull alone never reaches the plugin surface).
    spawned = []
    doctor._default_updater(
        spawn=lambda cmd: spawned.append(cmd) or 0,
        which=lambda name: "/usr/bin/claude" if name == "claude" else None,
    )
    assert ["claude", "plugin", "marketplace", "update", "sigma"] in spawned
    assert ["claude", "plugin", "update", "sigma@sigma"] in spawned


def test_default_updater_skips_plugin_when_claude_absent():
    # No `claude` binary → only the CLI git pull may run; no plugin commands.
    spawned = []
    doctor._default_updater(
        spawn=lambda cmd: spawned.append(cmd) or 0,
        which=lambda name: None,
    )
    assert not any("plugin" in cmd for cmd in spawned)


def test_fix_failure_keeps_fail_exit(capsys):
    # A fix that returns False should not flip the exit code to success.
    failing = [Check("deps", FAIL, "bad", fix=("try", lambda: False))]
    rc = doctor.run_doctor(
        run_all=lambda **k: failing, auto_yes=True, use_rich=False
    )
    assert rc == 1
