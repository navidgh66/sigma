"""Multi-model research engine: parallel fan-out + aggregation into research.md."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

from cli.models import ModelResult, available_models, run_model

RESEARCH_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Investigate this topic and return raw findings (data for aggregation, not a
human-facing reply):

TOPIC: {topic}

Return:
- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
"""


def build_prompt(topic: str) -> str:
    return RESEARCH_BRIEF.format(topic=topic)


def run_research(
    topic: str,
    models: List[str],
    runner: Callable = run_model,
    max_workers: int = 4,
) -> List[ModelResult]:
    """Fan out the research brief to each model in parallel.

    `runner` is injectable (defaults to models.run_model) for testing.
    """
    prompt = build_prompt(topic)
    requested = list(models)
    results: List[ModelResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {m: pool.submit(runner, m, prompt) for m in requested}
        for m in requested:
            results.append(futures[m].result())
    return results


def aggregate(topic: str, results: List[ModelResult], today: Optional[date] = None) -> str:
    """Combine model results into a single cited research.md document."""
    day = (today or date.today()).isoformat()
    ran = [r for r in results if r.ok]
    skipped = [r for r in results if r.skipped]
    failed = [r for r in results if not r.ok and not r.skipped]

    lines: List[str] = []
    lines.append(f"# Research: {topic}")
    lines.append("")
    lines.append(f"*Generated: {day} · Models run: {len(ran)} · "
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
    lines.append("> Cross-reference the per-model findings above. Promote claims "
                 "confirmed by 2+ models; flag single-source claims as unverified.")
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


def research(
    topic: str,
    requested_models: List[str],
    workspace: Path,
    runner: Callable = run_model,
    today: Optional[date] = None,
) -> Path:
    """End-to-end: resolve available models, fan out, aggregate, write file."""
    models = available_models(requested_models)
    # Still run requested-but-missing through runner so they record as skipped.
    to_run = requested_models if requested_models else models
    results = run_research(topic, to_run, runner=runner)
    content = aggregate(topic, results, today=today)
    return write_research(workspace, content)
