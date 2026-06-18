"""Tests for cli.gate — pluggable wakeAgent gate (skip work when nothing to do)."""

from __future__ import annotations

from cli import gate


def _spawn(stdout: str, code: int = 0):
    """Build an injectable runner returning canned (code, stdout)."""
    return lambda argv, cwd=None: (code, stdout)


def test_wake_true_proceeds():
    g = gate.run_gate("check.py", spawn=_spawn('{"wakeAgent": true}'))
    assert g.wake is True


def test_wake_false_skips():
    g = gate.run_gate("check.py", spawn=_spawn('{"wakeAgent": false}'))
    assert g.wake is False
    assert "skip" in g.reason.lower() or "gate" in g.reason.lower()


def test_wake_false_with_extra_output():
    out = "3 new files in inbox\n{\"wakeAgent\": false}\n"
    g = gate.run_gate("check.py", spawn=_spawn(out))
    assert g.wake is False


def test_non_json_defaults_wake():
    # Fail-safe: an unparseable gate must NOT silently skip real work.
    g = gate.run_gate("check.py", spawn=_spawn("garbage, no json here"))
    assert g.wake is True


def test_nonzero_exit_still_parses_skip():
    # If the script clearly says skip, honour it even on a non-zero exit.
    g = gate.run_gate("check.py", spawn=_spawn('{"wakeAgent": false}', code=2))
    assert g.wake is False


def test_spawn_error_defaults_wake():
    def boom(argv, cwd=None):
        raise OSError("cannot run gate")

    g = gate.run_gate("missing.py", spawn=boom)
    assert g.wake is True  # gate failure never blocks the pipeline
    assert "error" in g.reason.lower() or "fail" in g.reason.lower()


def test_no_gate_returns_wake():
    # No gate configured → always wake (gating is opt-in).
    g = gate.run_gate(None, spawn=_spawn('{"wakeAgent": false}'))
    assert g.wake is True


def test_reason_carries_script_text():
    g = gate.run_gate("check.py", spawn=_spawn('{"wakeAgent": false}'))
    assert isinstance(g.reason, str) and g.reason


def test_argv_passes_script_and_cwd(tmp_path):
    seen = {}

    def spy(argv, cwd=None):
        seen["argv"] = argv
        seen["cwd"] = cwd
        return (0, '{"wakeAgent": true}')

    gate.run_gate("my-check.py", cwd=tmp_path, spawn=spy)
    assert "my-check.py" in seen["argv"]
    assert seen["cwd"] == tmp_path
