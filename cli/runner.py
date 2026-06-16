"""Agent runner: execute a prompt through an agent CLI and capture the result.

This is the single execution chokepoint. Pipeline stages and loop cycles both
run through `AgentRunner.run`, so behavior (timeouts, capture, error handling)
is consistent and fully testable via an injected `runner` callable.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class AgentResult:
    ok: bool
    output: str
    error: Optional[str] = None
    returncode: int = 0


@dataclass
class AgentRunner:
    """Drives an agent CLI (default: claude). `runner` is injectable for tests."""

    executable: str = "claude"
    timeout: int = 1800
    runner: Callable = subprocess.run

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(self, prompt: str, cwd: Optional[Path] = None) -> AgentResult:
        """Run the agent non-interactively with the prompt; capture output."""
        if not self.available():
            return AgentResult(ok=False, output="", error=f"{self.executable} CLI not found")
        argv = [self.executable, "-p", prompt]
        try:
            proc = self.runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError:
            return AgentResult(ok=False, output="", error=f"{self.executable} not found at run time")
        except subprocess.TimeoutExpired:
            return AgentResult(ok=False, output="", error=f"timed out after {self.timeout}s")

        out = (getattr(proc, "stdout", "") or "").strip()
        if proc.returncode != 0:
            err = (getattr(proc, "stderr", "") or "").strip() or f"exit code {proc.returncode}"
            return AgentResult(ok=False, output=out, error=err, returncode=proc.returncode)
        return AgentResult(ok=True, output=out, returncode=0)


def write_artifact(path: Path, content: str) -> Path:
    """Write agent output to an artifact path, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
