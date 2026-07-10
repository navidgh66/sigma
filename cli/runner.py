"""Agent runner: execute a prompt through an agent CLI and capture the result.

This is the single execution chokepoint. Pipeline stages and loop cycles both
run through `AgentRunner.run`, so behavior (timeouts, capture, error handling)
is consistent and fully testable via an injected `runner` callable.
"""

from __future__ import annotations

import shutil
import subprocess
import time
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

    Two optional, independent extensions (both default to the prior behavior, so
    a bare `AgentRunner()` is byte-identical to before):

    - `model`: when set, `--model <alias>` is injected into the argv (e.g. "haiku"
      / "sonnet" / "opus"). The alias is passed straight through to the CLI — no
      model-ID map to drift. Powers the cost loop's intelligent model routing.
    - `trajectory_sink`: a `Callable[[dict], None]` called once per run with a
      step record (role, model, ok, verdict-free metadata, duration). Best-effort
      observability — a failing sink NEVER breaks the run (the inverse of a hard
      gate). `clock` supplies timestamps; `time.monotonic` by default.

    Two more optional fields extend this to non-claude-shaped CLIs (e.g. codex,
    whose argv is `exec --sandbox <mode> ...`, not `-p ...`), both additive:

    - `argv_builder`: `Callable[[str, Optional[str]], List[str]]`. When set, fully
      replaces the built-in `[-p, --model, prompt]` argv construction — called as
      `argv_builder(prompt, self.model)`, its return value used as-is.
    - `output_cleaner`: `Callable[[str], str]`. When set, applied to the raw
      (unstripped) stdout before it becomes `AgentResult.output` — e.g. to strip
      a CLI's session-metadata preamble (codex's `workdir:`/`tokens used:` lines)
      that would otherwise corrupt a verifier's `VERDICT:` parsing.
    """

    executable: str = "claude"
    timeout: int = 1800
    runner: Callable = subprocess.run
    model: Optional[str] = None
    trajectory_sink: Optional[Callable[[dict], None]] = None
    clock: Callable[[], float] = time.monotonic
    argv_builder: Optional[Callable[[str, Optional[str]], list]] = None
    output_cleaner: Optional[Callable[[str], str]] = None

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _default_argv(self, prompt: str) -> list:
        argv = [self.executable, "-p"]
        if self.model:
            argv += ["--model", self.model]
        argv.append(prompt)
        return argv

    def run(self, prompt: str, cwd: Optional[Path] = None, role: str = "agent") -> AgentResult:
        """Run the agent non-interactively with the prompt; capture output.

        `role` labels the step for trajectory capture (implementer / verifier /
        logic / test-writer / stage name). It does not affect the argv.
        """
        if not self.available():
            result = AgentResult(ok=False, output="", error=f"{self.executable} CLI not found")
            self._emit(role, result, duration=0.0)
            return result

        argv = self.argv_builder(prompt, self.model) if self.argv_builder else self._default_argv(prompt)

        start = self.clock()
        try:
            proc = self.runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError:
            result = AgentResult(ok=False, output="", error=f"{self.executable} not found at run time")
            self._emit(role, result, self.clock() - start)
            return result
        except subprocess.TimeoutExpired:
            result = AgentResult(ok=False, output="", error=f"timed out after {self.timeout}s")
            self._emit(role, result, self.clock() - start)
            return result

        duration = self.clock() - start
        raw_out = getattr(proc, "stdout", "") or ""
        out = self.output_cleaner(raw_out) if self.output_cleaner else raw_out.strip()
        if proc.returncode != 0:
            err = (getattr(proc, "stderr", "") or "").strip() or f"exit code {proc.returncode}"
            result = AgentResult(ok=False, output=out, error=err, returncode=proc.returncode)
        else:
            result = AgentResult(ok=True, output=out, returncode=0)
        self._emit(role, result, duration)
        return result

    def _emit(self, role: str, result: AgentResult, duration: float) -> None:
        """Best-effort: hand one step record to the trajectory sink. Never raises."""
        if self.trajectory_sink is None:
            return
        step = {
            "role": role,
            "model": self.model,
            "ok": result.ok,
            "returncode": result.returncode,
            "error": result.error,
            "output_chars": len(result.output or ""),
            "duration_s": round(duration, 3),
        }
        try:
            self.trajectory_sink(step)
        except Exception:  # noqa: BLE001 — observability must never break the run
            pass


def write_artifact(path: Path, content: str) -> Path:
    """Write agent output to an artifact path, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
