"""Model-provider adapters: invoke the Claude and GPT (Codex) CLIs as research
subprocesses (tier 1 of sigma's two-tier research providers — see
cli/search_providers.py for tier 2, HTTP search tools).

Each adapter knows how to (a) detect whether its CLI is installed, (b) build an
argv (prompt passed via argv, never the shell — no injection risk), and (c) clean
the CLI's raw stdout into plain text for aggregation. Missing CLIs degrade
gracefully — the research engine skips them and records that they were skipped.

Both providers are driven through their subscription-backed CLIs (no paid API
keys required):
  - claude → `claude -p`            (Claude subscription)
  - gpt    → `codex exec`           (ChatGPT subscription via Codex CLI)

A `--deep` mode (see cli/research.py) appends each adapter's `deep_args` to turn
on live web search / grounding.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Timeouts (seconds): quick is a from-memory pass; deep does live web research.
QUICK_TIMEOUT = 300
DEEP_TIMEOUT = 900


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
    # argv builder: {exe} → the binary, {prompt} → the research brief (one argv
    # element, never shell-split).
    arg_template: List[str]
    # Extra argv appended only in --deep mode (enables web search / grounding).
    deep_args: List[str] = field(default_factory=list)
    # Extra argv (template: {model}) injected right after the executable when a
    # model_alias is passed. Empty for adapters with no alias-passthrough
    # --model contract (codex) — the alias is then ignored, mirroring
    model_args: List[str] = field(default_factory=list)

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def build_argv(
        self,
        prompt: str,
        deep: bool = False,
        sandbox: str = "read-only",
        model_alias: Optional[str] = None,
    ) -> List[str]:
        argv = [
            self.executable if a == "{exe}"
            else a.replace("{sandbox}", sandbox).replace("{prompt}", prompt)
            for a in self.arg_template
        ]
        if model_alias and self.model_args:
            argv[1:1] = [a.replace("{model}", model_alias) for a in self.model_args]
        if deep:
            argv.extend(self.deep_args)
        return argv


# Registry of known adapters. arg_template uses {exe} for the binary and
# {prompt} for the research brief.
ADAPTERS: Dict[str, ModelAdapter] = {
    "claude": ModelAdapter(
        name="claude",
        executable="claude",
        arg_template=["{exe}", "-p", "{prompt}"],
        # claude has no web-search CLI flag; the deep brief instructs it instead.
        deep_args=[],
        model_args=["--model", "{model}"],
    ),
    "gpt": ModelAdapter(
        name="gpt",
        executable="codex",
        # `codex exec` runs non-interactively, subscription-backed (ChatGPT login).
        # {sandbox} defaults to read-only via build_argv; the loop's codex-backed
            arg_template=["{exe}", "exec", "--sandbox", "{sandbox}", "--color", "never", "{prompt}"],
        # Enable Codex's built-in web_search tool for deep research.
        deep_args=["-c", "tools.web_search=true"],
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


def clean_output(model: str, raw: str) -> str:
    """Normalize a CLI's raw stdout into plain findings text.

    - gpt (codex): strip event/preamble noise, keeping the agent's final message.
    - claude: passthrough.
    """
    raw = raw or ""
    if model == "gpt":
        return _clean_codex(raw)
    return raw.strip()


def _clean_codex(raw: str) -> str:
    """Strip codex exec's session/event preamble, keeping the substantive output.

    `codex exec` prints session metadata lines (workdir, model, tokens used,
    `[timestamp] ...` events) interleaved with the agent's actual reply. We drop
    obvious metadata/event lines and keep the prose. On an empty result, return
    the stripped raw so nothing is silently lost.
    """
    text = raw.strip()
    if not text:
        return ""
    kept: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        # Drop codex metadata/event lines.
        lower = stripped.lower()
        if stripped.startswith("[") and "]" in stripped[:30]:
            # `[2026-06-18T...] event` style log lines.
            continue
        if lower.startswith(("workdir:", "model:", "provider:", "approval:",
                             "sandbox:", "reasoning:", "tokens used:", "session id:",
                             "user instructions:", "--------")):
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return cleaned or text


def run_model(
    model: str,
    prompt: str,
    timeout: Optional[int] = None,
    deep: bool = False,
    model_alias: Optional[str] = None,
    runner=subprocess.run,
) -> ModelResult:
    """Run one model's CLI with the prompt. `runner` is injectable for tests.

    `deep` enables web search / grounding (appends the adapter's deep_args and
    uses the longer deep timeout unless an explicit timeout is given).
    """
    adapter = ADAPTERS.get(model)
    if adapter is None:
        return ModelResult(model=model, ok=False, text="", error="unknown model", skipped=True)
    if not adapter.available():
        return ModelResult(model=model, ok=False, text="", error="CLI not installed", skipped=True)

    if timeout is None:
        timeout = DEEP_TIMEOUT if deep else QUICK_TIMEOUT

    argv = adapter.build_argv(prompt, deep=deep, model_alias=model_alias)
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
            text=clean_output(model, proc.stdout or ""),
            error=(proc.stderr or "").strip() or f"exit code {proc.returncode}",
        )
    return ModelResult(model=model, ok=True, text=clean_output(model, proc.stdout or ""))
