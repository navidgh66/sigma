"""Keep the Mac awake during long sigma runs via macOS `caffeinate`.

Long autonomous work (`sigma loop --execute`, `sigma hermes --auto`) can outlast
the display/idle sleep timer. `keep_awake` wraps such work in a context manager
that spawns `caffeinate` for its duration and tears it down afterwards — even on
exception. No-ops cleanly off macOS or when caffeinate is absent, so callers can
pass the flag unconditionally.

The spawn/availability hooks are injectable, so the whole thing is testable
without launching a real process.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
from typing import Callable, List, Optional

# -d display, -i idle, -m disk, -s system (on AC), -u declare user active.
_FLAGS = "-dimsu"


def is_macos() -> bool:
    return sys.platform == "darwin"


def available() -> bool:
    """True only on macOS with caffeinate on PATH."""
    return is_macos() and shutil.which("caffeinate") is not None


def caffeinate_argv(seconds: Optional[int] = None) -> List[str]:
    """Build the caffeinate command. `seconds` adds a hard timeout (-t)."""
    argv = ["caffeinate", _FLAGS]
    if seconds is not None:
        argv += ["-t", str(int(seconds))]
    return argv


def _default_spawn(argv: List[str]):
    # Detached enough to outlive nothing — we own its lifetime in the context.
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@contextlib.contextmanager
def keep_awake(
    enabled: bool = True,
    seconds: Optional[int] = None,
    spawn: Callable = _default_spawn,
    available: Callable[[], bool] = available,
):
    """Context manager that holds the Mac awake while the block runs.

    Spawns caffeinate on enter, terminates it on exit (including on exception).
    No-ops when `enabled` is False or caffeinate is unavailable. A failure to
    spawn is swallowed — keeping the Mac awake is best-effort, never fatal.
    """
    proc = None
    if enabled and available():
        try:
            proc = spawn(caffeinate_argv(seconds))
        except OSError:
            proc = None
    try:
        yield proc
    finally:
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()
                proc.wait(timeout=5)
