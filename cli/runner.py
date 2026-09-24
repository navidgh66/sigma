"""Agent runner: execute a prompt through an agent CLI and capture the result.

This is the single execution chokepoint for sigma's CLI agent runs (review,
profile, learn, claude-md check/create), so behavior (timeouts, capture, error
handling) is consistent and fully testable via an injected `runner` callable.
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
    """Drives an agent CLI (default: claude). `runner` is injectable for tests.

    `model`, when set, injects `--model <alias>` into the argv (e.g. "haiku" /
    "sonnet" / "opus"); the alias is passed straight through to the CLI.
    """

    executable: str = "claude"
    timeout: int = 1800
    runner: Callable = subprocess.run
    model: Optional[str] = None

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _argv(self, prompt: str) -> list:
        argv = [self.executable, "-p"]
        if self.model:
            argv += ["--model", self.model]
        argv.append(prompt)
        return argv

    def run(self, prompt: str, cwd: Optional[Path] = None, role: str = "agent") -> AgentResult:
        """Run the agent non-interactively with the prompt; capture output.

        `role` is accepted for caller readability; it does not affect the run.
        """
        if not self.available():
            return AgentResult(ok=False, output="", error=f"{self.executable} CLI not found")
        try:
            proc = self.runner(
                self._argv(prompt),
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
