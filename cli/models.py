"""Model adapters: invoke Claude / Gemini / GPT CLIs as research subprocesses.

Each adapter knows how to (a) detect whether its CLI is installed and (b) run a
research prompt and return text. Missing CLIs degrade gracefully — the research
engine skips them and records that they were skipped.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelResult:
    model: str
    ok: bool
    text: str
    error: Optional[str] = None
    skipped: bool = False


@dataclass
class ModelAdapter:
    """Describes how to drive one model CLI."""

    name: str
    executable: str
    # argv builder: given a prompt, return the command list. {prompt} is passed
    # via argv, never the shell, so no injection risk.
    arg_template: List[str]

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def build_argv(self, prompt: str) -> List[str]:
        return [self.executable if a == "{exe}" else a.replace("{prompt}", prompt) for a in self.arg_template]


# Registry of known adapters. arg_template uses {exe} for the binary and
# {prompt} for the research brief.
ADAPTERS: Dict[str, ModelAdapter] = {
    "claude": ModelAdapter(
        name="claude",
        executable="claude",
        arg_template=["{exe}", "-p", "{prompt}"],
    ),
    "gemini": ModelAdapter(
        name="gemini",
        executable="gemini",
        arg_template=["{exe}", "-p", "{prompt}"],
    ),
    "gpt": ModelAdapter(
        name="gpt",
        executable="openai",
        arg_template=[
            "{exe}", "api", "chat.completions.create",
            "-m", "gpt-4o", "-g", "user", "{prompt}",
        ],
    ),
}


def available_models(requested: List[str]) -> List[str]:
    """Return requested models whose CLI is installed, preserving order."""
    out: List[str] = []
    for m in requested:
        adapter = ADAPTERS.get(m)
        if adapter and adapter.available():
            out.append(m)
    return out


def run_model(
    model: str,
    prompt: str,
    timeout: int = 300,
    runner=subprocess.run,
) -> ModelResult:
    """Run one model's CLI with the prompt. `runner` is injectable for tests."""
    adapter = ADAPTERS.get(model)
    if adapter is None:
        return ModelResult(model=model, ok=False, text="", error="unknown model", skipped=True)
    if not adapter.available():
        return ModelResult(model=model, ok=False, text="", error="CLI not installed", skipped=True)

    argv = adapter.build_argv(prompt)
    try:
        proc = runner(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return ModelResult(model=model, ok=False, text="", error="CLI not found at run time", skipped=True)
    except subprocess.TimeoutExpired:
        return ModelResult(model=model, ok=False, text="", error=f"timed out after {timeout}s")

    if proc.returncode != 0:
        return ModelResult(
            model=model,
            ok=False,
            text=proc.stdout or "",
            error=(proc.stderr or "").strip() or f"exit code {proc.returncode}",
        )
    return ModelResult(model=model, ok=True, text=(proc.stdout or "").strip())
