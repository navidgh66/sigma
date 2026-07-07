"""Multi-model research engine: parallel fan-out + aggregation into research.md."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

from cli.models import ModelResult, available_models, run_model
from cli.research_brief import build_prompt
from cli.search_providers import available_tools, run_search_tool


def run_research(
    topic: str,
    models: List[str],
    tools: Optional[List[str]] = None,
    runner: Callable = run_model,
    search_runner: Callable = run_search_tool,
    max_workers: int = 4,
    deep: bool = False,
    web: bool = False,
) -> List[ModelResult]:
    """Fan out the research brief to each model CLI and each search tool in
    parallel.

    `runner`/`search_runner` are injectable for testing. `tools` defaults to
    none requested (regression-safe: today's exact behavior when omitted).
    `deep` selects the exhaustive web-grounded brief; `web` selects a lighter
    quick web-grounded brief; either enables the model adapters' web-search
    path. Search tools are always grounded regardless of deep/web.
    """
    prompt = build_prompt(topic, deep=deep, web=web)
    requested_models = list(models)
    requested_tools = list(tools or [])
    web_search = deep or web
    results: List[ModelResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        model_futures = {
            m: pool.submit(_call_runner, runner, m, prompt, web_search) for m in requested_models
        }
        tool_futures = {t: pool.submit(search_runner, t, prompt) for t in requested_tools}
        for m in requested_models:
            results.append(model_futures[m].result())
        for t in requested_tools:
            results.append(tool_futures[t].result())
    return results


def _call_runner(runner: Callable, model: str, prompt: str, deep: bool) -> ModelResult:
    """Invoke `runner` with the standard (model, prompt, deep=) signature."""
    return runner(model, prompt, deep=deep)


_SYNTHESIS_PROMPT = """You are cross-referencing raw research findings for the
topic below. Promote any claim confirmed by 2 or more sources; explicitly flag
single-source claims as unverified. Return the synthesis as plain prose.

TOPIC: {topic}

FINDINGS:
{findings}
"""

_SYNTHESIS_FALLBACK = (
    "> Cross-reference the per-model findings above. Promote claims "
    "confirmed by 2+ models; flag single-source claims as unverified."
)


def synthesize(topic: str, results: List[ModelResult], runner: Callable[[str], str]) -> str:
    """One distinct LLM call over all raw findings, cross-referencing claims.

    `runner` takes a single prompt string and returns the synthesis text — a
    simpler signature than the model/search runners since this is one call,
    not a fan-out. On any failure (raises, times out, returns falsy), falls
    back to the static placeholder — degrade, never crash the whole doc.
    """
    ran = [r for r in results if r.ok]
    if not ran:
        return _SYNTHESIS_FALLBACK
    findings_block = "\n\n".join(f"### {r.model}\n{r.text.strip()}" for r in ran)
    prompt = _SYNTHESIS_PROMPT.format(topic=topic, findings=findings_block)
    try:
        body = runner(prompt)
    except Exception:  # noqa: BLE001 — synthesis failure must never break the doc
        return _SYNTHESIS_FALLBACK
    if not body or not body.strip():
        return _SYNTHESIS_FALLBACK
    return body.strip()


def aggregate(
    topic: str,
    results: List[ModelResult],
    today: Optional[date] = None,
    deep: bool = False,
    web: bool = False,
    synthesis_runner: Optional[Callable[[str], str]] = None,
) -> str:
    """Combine model results into a single cited research.md document."""
    day = (today or date.today()).isoformat()
    ran = [r for r in results if r.ok]
    skipped = [r for r in results if r.skipped]
    failed = [r for r in results if not r.ok and not r.skipped]
    if deep:
        mode = "deep (web-grounded)"
    elif web:
        mode = "web (quick web-grounded)"
    else:
        mode = "quick"

    lines: List[str] = []
    lines.append(f"# Research: {topic}")
    lines.append("")
    lines.append(f"*Generated: {day} · Mode: {mode} · Models run: {len(ran)} · "
                 f"Skipped: {len(skipped)} · Failed: {len(failed)}*")
    lines.append("")

    # Transparency: which models contributed (no silent caps).
    lines.append("## Model coverage")
    lines.append("")
    for r in results:
        if r.ok:
            status = "✅ ran"
        elif r.skipped:
            status = f"⏭️ skipped ({r.error})"
        else:
            status = f"❌ failed ({r.error})"
        lines.append(f"- **{r.model}**: {status}")
    lines.append("")

    if not ran:
        lines.append("## ⚠️ No models produced findings")
        lines.append("")
        lines.append("Every requested model was skipped or failed. Install at least "
                     "one model CLI (claude / gemini / openai) and retry.")
        lines.append("")
        return "\n".join(lines)

    # Per-model findings (raw), labeled for later human synthesis.
    lines.append("## Findings by model")
    lines.append("")
    for r in ran:
        lines.append(f"### {r.model}")
        lines.append("")
        lines.append(r.text.strip() or "_(empty response)_")
        lines.append("")

    lines.append("## Synthesis")
    lines.append("")
    if synthesis_runner is not None:
        lines.append(synthesize(topic, results, runner=synthesis_runner))
    else:
        lines.append(_SYNTHESIS_FALLBACK)
    lines.append("")
    lines.append("## Next")
    lines.append("")
    lines.append("→ `/propose`")
    lines.append("")
    return "\n".join(lines)


def write_research(workspace: Path, content: str) -> Path:
    """Write research.md into the spec workspace, creating dirs as needed."""
    workspace.mkdir(parents=True, exist_ok=True)
    out = workspace / "research.md"
    out.write_text(content)
    return out


def _read_manual_findings(workspace: Path) -> List[ModelResult]:
    """Read pre-completed findings dropped as markdown into workspace/manual/.

    Each *.md file becomes one ModelResult (model="manual:<filename>", ok=True).
    Missing manual/ dir → empty list (fail-safe, matches every other optional
    input in this module).
    """
    manual_dir = workspace / "manual"
    if not manual_dir.is_dir():
        return []
    results: List[ModelResult] = []
    for path in sorted(manual_dir.glob("*.md")):
        try:
            text = path.read_text().strip()
        except (OSError, UnicodeDecodeError):
            continue
        if text:
            results.append(ModelResult(model=f"manual:{path.name}", ok=True, text=text))
    return results


def research(
    topic: str,
    requested_models: List[str],
    workspace: Path,
    runner: Callable = run_model,
    requested_tools: Optional[List[str]] = None,
    today: Optional[date] = None,
    deep: bool = False,
    web: bool = False,
    synthesis_runner: Optional[Callable[[str], str]] = None,
) -> Path:
    """End-to-end: resolve available models/tools, fan out, read manual
    findings, aggregate + synthesize, write file.
    """
    to_run = requested_models if requested_models else available_models(requested_models)
    to_run_tools = available_tools(requested_tools or [])
    results = run_research(topic, to_run, tools=to_run_tools, runner=runner, deep=deep, web=web)
    results += _read_manual_findings(workspace)
    content = aggregate(
        topic, results, today=today, deep=deep, web=web, synthesis_runner=synthesis_runner
    )
    return write_research(workspace, content)
