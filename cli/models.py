"""Model-provider adapters: invoke Claude / Gemini / GPT CLIs as research
subprocesses (tier 1 of sigma's two-tier research providers — see
cli/search_providers.py for tier 2, HTTP search tools).

Each adapter knows how to (a) detect whether its CLI is installed, (b) build an
argv (prompt passed via argv, never the shell — no injection risk), and (c) clean
the CLI's raw stdout into plain text for aggregation. Missing CLIs degrade
gracefully — the research engine skips them and records that they were skipped.

All three providers are driven through their subscription-backed CLIs (no paid
API keys required):
  - claude → `claude -p`            (Claude subscription)
  - gemini → `gemini -p --output-format json`  (Google OAuth quota)
  - gpt    → `codex exec`           (ChatGPT subscription via Codex CLI)

A `--deep` mode (see cli/research.py) appends each adapter's `deep_args` to turn
on live web search / grounding.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

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

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def build_argv(self, prompt: str, deep: bool = False, sandbox: str = "read-only") -> List[str]:
        argv = [
            self.executable if a == "{exe}"
            else a.replace("{sandbox}", sandbox).replace("{prompt}", prompt)
            for a in self.arg_template
        ]
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
    ),
    "gemini": ModelAdapter(
        name="gemini",
        executable="gemini",
        arg_template=["{exe}", "-p", "{prompt}", "--output-format", "json"],
        # Gemini CLI grounds via Google Search; deep mode is driven by the brief
        # plus (where supported) the CLI's default grounding.
        deep_args=[],
    ),
    "gpt": ModelAdapter(
        name="gpt",
        executable="codex",
        # `codex exec` runs non-interactively, subscription-backed (ChatGPT login).
        # {sandbox} defaults to read-only via build_argv; the loop's codex-backed
        # test-writer role passes "workspace-write" instead (see codex_argv_builder).
        arg_template=["{exe}", "exec", "--sandbox", "{sandbox}", "--color", "never", "{prompt}"],
        # Enable Codex's built-in web_search tool for deep research.
        deep_args=["-c", "tools.web_search=true"],
    ),
}


def codex_argv_builder(sandbox: str) -> Callable[[str, Optional[str]], List[str]]:
    """Build an `AgentRunner.argv_builder`-shaped callable for a codex-backed role.

    `model` is accepted (to match AgentRunner's argv_builder signature) but
    ignored — codex's CLI has no alias-passthrough `--model` contract like
    claude's, so forcing a sigma model-tier alias through it would silently
    break if the alias isn't a real codex model name.
    """

    def build(prompt: str, model: Optional[str]) -> List[str]:
        return ADAPTERS["gpt"].build_argv(prompt, sandbox=sandbox)

    return build


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

    - gemini: parse the JSON envelope and extract the response text; fall back to
      raw on any parse failure (never crash the fan-out).
    - gpt (codex): strip event/preamble noise, keeping the agent's final message.
    - claude: passthrough.
    """
    raw = raw or ""
    if model == "gemini":
        return _clean_gemini(raw)
    if model == "gpt":
        return _clean_codex(raw)
    return raw.strip()


def _clean_gemini(raw: str) -> str:
    """Extract text from `gemini --output-format json` output.

    The CLI emits a JSON object; the response lives under "response" (newer CLIs)
    or nested in a candidates/parts structure. Fall back to raw text on failure.
    """
    text = raw.strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    if isinstance(data, dict):
        # Newer Gemini CLI: {"response": "..."} (possibly with stats/other keys).
        resp = data.get("response")
        if isinstance(resp, str) and resp.strip():
            return resp.strip()
        # Fallback: dig into candidates → content → parts → text.
        parts_text = _gemini_candidates_text(data)
        if parts_text:
            return parts_text
    return text


def _gemini_candidates_text(data: dict) -> str:
    """Pull concatenated part text from a candidates/content/parts structure."""
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        return ""
    chunks: List[str] = []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


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

    argv = adapter.build_argv(prompt, deep=deep)
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
