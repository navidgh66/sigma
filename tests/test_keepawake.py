"""Tests for cli.keepawake — caffeinate wrapper that prevents Mac sleep."""

from __future__ import annotations

from cli import keepawake


class FakeProc:
    def __init__(self):
        self.terminated = False
        self.waited = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited = True


def test_argv_default_flags():
    argv = keepawake.caffeinate_argv()
    assert argv[0] == "caffeinate"
    # -i prevent idle sleep, -m disk, -s system, -d display
    assert "-dimsu" in argv or {"-d", "-i", "-m", "-s"} <= set(argv)


def test_argv_with_timeout():
    argv = keepawake.caffeinate_argv(seconds=3600)
    assert "-t" in argv
    assert "3600" in argv


def test_keep_awake_spawns_and_terminates():
    spawned = []
    proc = FakeProc()

    def fake_spawn(argv):
        spawned.append(argv)
        return proc

    with keepawake.keep_awake(enabled=True, spawn=fake_spawn, available=lambda: True):
        assert spawned and spawned[0][0] == "caffeinate"
    assert proc.terminated is True


def test_keep_awake_disabled_does_not_spawn():
    spawned = []
    with keepawake.keep_awake(
        enabled=False, spawn=lambda a: spawned.append(a), available=lambda: True
    ):
        pass
    assert spawned == []


def test_keep_awake_unavailable_does_not_spawn():
    spawned = []
    with keepawake.keep_awake(
        enabled=True, spawn=lambda a: spawned.append(a), available=lambda: False
    ):
        pass
    assert spawned == []


def test_keep_awake_terminates_even_on_exception():
    proc = FakeProc()
    try:
        with keepawake.keep_awake(enabled=True, spawn=lambda a: proc, available=lambda: True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert proc.terminated is True


def test_keep_awake_survives_spawn_failure():
    def bad_spawn(argv):
        raise OSError("no caffeinate")

    # Must not crash the wrapped work if caffeinate can't start.
    with keepawake.keep_awake(enabled=True, spawn=bad_spawn, available=lambda: True):
        pass
