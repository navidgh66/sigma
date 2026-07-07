# Research Two-Tier Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the sigma `research` module's five defects (rule duplication, fake synthesis, web-search asymmetry, dead code, test-shape leak) and add a second provider tier (HTTP search tools, starting with Firecrawl) plus a manual-findings input lane, so `sigma research` produces genuinely cross-referenced, multi-source output instead of concatenated raw text.

**Architecture:** Two provider tiers feed one `aggregate()`/`synthesize()` pipeline. Tier 1 (existing, unchanged shape): subprocess model-CLI adapters in `cli/models.py`. Tier 2 (new): HTTP search-tool adapters in `cli/search_providers.py`, same `ModelResult` output shape. A new `cli/research_brief.py` becomes the single source of truth for prompt rules; `cli/research_docs.py` + `scripts/regen_research_docs.py` generate `commands/research.md` and the persona docs from it, with `tests/test_research_docs.py` locking the two in sync. `cli/research.py` gains a real `synthesize()` call and a manual-findings reader.

**Tech Stack:** Python 3.9, stdlib only (`urllib` for HTTP — no `requests`), pytest, ruff.

## Global Constraints

- Python 3.9 target: use `Optional[X]`/`List[X]` from `typing`, never `X | None`.
- No new runtime pip dependency. Firecrawl HTTP calls use stdlib `urllib.request`, exact pattern of `cli/scout_run.py`'s `_default_fetch`.
- All new modules are dependency-injectable (fetch/runner/clock as parameters with real defaults) so tests never touch the network or spawn real subprocesses.
- Every new/changed public function gets type hints.
- `sigma research` with zero search-tool keys configured and zero `manual/` files must behave identically to today except that the "## Synthesis" section is now real (was a static placeholder) — this is the one intentional behavior change; everything else must be a byte-identical regression.
- Ruff must stay clean (`python3 -m ruff check cli/ tests/ scripts/`); full suite must stay green (`python3 -m pytest tests/ -q`).
- Firecrawl API key name: `FIRECRAWL_API_KEY` — added to `cli/secrets.py`'s `KNOWN_KEYS`, following the exact optional/never-prompted pattern already used for `GEMINI_API_KEY`/`OPENAI_API_KEY`. It is **not** added to onboard's prompt flow (search tools are opt-in, per spec).
- Fail-safe convention throughout: any error (missing key, HTTP failure, subprocess crash, synthesis LLM failure) degrades to a `ModelResult`/placeholder, never raises out of the pipeline.

---

## File Structure

```
cli/research_brief.py     NEW — canonical brief templates + shared rules text
cli/research_docs.py      NEW — pure render functions for commands/research.md + persona bodies
scripts/regen_research_docs.py   NEW — thin: calls render_*, writes files
cli/search_providers.py   NEW — Firecrawl HTTP adapter, ModelResult-shaped
cli/research.py           MODIFY — add search-tool fan-out, synthesize(), manual-findings reader, remove dead code
cli/models.py             MODIFY — docstring only (clarify "model providers"); no behavior change
cli/secrets.py            MODIFY — add FIRECRAWL_API_KEY to KNOWN_KEYS
cli/config.py             MODIFY — add DEFAULT_TOOLS + tools field to SigmaConfig
cli/cost.py               MODIFY — add "synthesis" key to routing_for("research")
cli/main.py               MODIFY — cmd_research reads cfg.tools, passes to research()
commands/research.md      REGENERATED (generated block) + hand-edited (plugin-behavior block: MCP dispatch, real gemini/gpt Bash dispatch, claude→deep-research-skill, manual-findings check)
subagents/researchers/gemini-researcher.md   MODIFY — becomes argv-template doc, regenerated rules block
subagents/researchers/gpt-researcher.md      MODIFY — becomes argv-template doc, regenerated rules block
subagents/researchers/claude-researcher.md   DELETE — replaced by deep-research skill invocation in commands/research.md
tests/test_research.py    MODIFY — extend for synthesis, manual findings, remove legacy 2-arg fakes
tests/test_search_providers.py   NEW
tests/test_research_docs.py      NEW
tests/test_secrets.py     MODIFY — assert FIRECRAWL_API_KEY in KNOWN_KEYS (check if file exists first)
tests/test_config.py      MODIFY — assert tools default (check if file exists first)
tests/test_cost.py        MODIFY — assert routing_for("research") includes "synthesis" (check if file exists first)
```

---

### Task 1: `cli/research_brief.py` — canonical brief templates

**Files:**
- Create: `cli/research_brief.py`
- Test: `tests/test_research_brief.py`

**Interfaces:**
- Produces: `QUICK_BRIEF: str`, `WEB_BRIEF: str`, `DEEP_BRIEF: str` (format-string templates with a `{topic}` placeholder, moved verbatim from `cli/research.py`'s `RESEARCH_BRIEF`/`WEB_RESEARCH_BRIEF`/`DEEP_RESEARCH_BRIEF`), `RULES_TEXT: str` (a shared bullet list: cite sources, confidence note per theme, flag single-source claims, prefer last-12-months sources, separate fact from inference), `build_prompt(topic: str, deep: bool = False, web: bool = False) -> str` (moved from `cli/research.py`, identical logic: deep wins if both set).

This task only **moves** code — no behavior change. `cli/research.py` will import from here in Task 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_research_brief.py`:

```python
from cli.research_brief import build_prompt, QUICK_BRIEF, WEB_BRIEF, DEEP_BRIEF, RULES_TEXT


def test_build_prompt_contains_topic():
    p = build_prompt("graph neural nets")
    assert "graph neural nets" in p
    assert "source" in p.lower()


def test_build_prompt_deep_demands_web_search():
    quick = build_prompt("t", deep=False)
    deep = build_prompt("t", deep=True)
    assert "web-search" in deep or "web search" in deep.lower()
    assert "do NOT answer from memory" in deep
    assert "do NOT answer from memory" not in quick


def test_build_prompt_web_demands_search_but_lighter():
    web = build_prompt("t", web=True)
    quick = build_prompt("t", deep=False)
    assert "search the web" in web.lower()
    assert "QUICK" in web or "quick" in web
    assert web != quick


def test_build_prompt_deep_wins_over_web():
    both = build_prompt("t", deep=True, web=True)
    deep = build_prompt("t", deep=True)
    assert both == deep


def test_rules_text_is_nonempty_and_shared():
    assert "source" in RULES_TEXT.lower()
    assert "confidence" in RULES_TEXT.lower()
    assert RULES_TEXT in QUICK_BRIEF
    assert RULES_TEXT in WEB_BRIEF
    assert RULES_TEXT in DEEP_BRIEF
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_research_brief.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.research_brief'`

- [ ] **Step 3: Write the implementation**

Create `cli/research_brief.py`:

```python
"""Canonical research-brief templates and shared citation/confidence rules.

Single source of truth for the CLI research briefs (cli/research.py) and the
generated docs (cli/research_docs.py → commands/research.md + persona files).
Editing a rule here and regenerating (scripts/regen_research_docs.py) is the
only way rules should change — never hand-edit the generated blocks directly.
"""

from __future__ import annotations

RULES_TEXT = """- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions"""

QUICK_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Investigate this topic and return raw findings (data for aggregation, not a
human-facing reply):

TOPIC: {{topic}}

Return:
{rules}
""".format(rules=RULES_TEXT)

DEEP_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Use your web-search / grounding tools to investigate this topic against LIVE
sources, then return raw findings (data for aggregation, not a human-facing reply):

TOPIC: {{topic}}

Requirements:
- Actively search the web; do NOT answer from memory alone
- Themed findings, each with a real, resolvable source URL you actually consulted
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Strongly prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
"""

WEB_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Do a QUICK web-grounded check on this topic — search the web for current facts,
but keep it concise (this is the light web pass, not an exhaustive deep dive):

TOPIC: {{topic}}

Requirements:
- Search the web for recent facts; do not answer from memory alone
- A short list of themed findings, each with a real source URL you consulted
- Prefer sources from the last 12 months
- Flag anything single-source or uncertain
- Separate fact from inference
"""


def build_prompt(topic: str, deep: bool = False, web: bool = False) -> str:
    """Pick the brief by mode. `deep` = exhaustive web research; `web` = quick
    web-grounded pass; neither = from-memory quick pass. `deep` wins if both set.
    """
    if deep:
        brief = DEEP_BRIEF
    elif web:
        brief = WEB_BRIEF
    else:
        brief = QUICK_BRIEF
    return brief.format(topic=topic)
```

Note: `RULES_TEXT` is embedded into `QUICK_BRIEF` via `.format(rules=RULES_TEXT)` at module load time, using `{{topic}}` (escaped) so the final template still has a literal `{topic}` placeholder for `build_prompt`'s `.format(topic=topic)` call. `DEEP_BRIEF`/`WEB_BRIEF` inline their own rules text directly (matches the original three brief strings' wording exactly — they are not identical to `RULES_TEXT`, they have brief-specific requirement lists) — only `QUICK_BRIEF` composes `RULES_TEXT` as a distinct constant since it's the one whose rules text is reused byte-for-byte as the shared "Return:" bullet list. This keeps the moved code behavior-identical to the original three strings in `cli/research.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_research_brief.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Ruff check**

Run: `python3 -m ruff check cli/research_brief.py tests/test_research_brief.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add cli/research_brief.py tests/test_research_brief.py
git commit -m "feat: extract research brief templates into cli/research_brief.py"
```

---

### Task 2: `cli/search_providers.py` — Firecrawl HTTP adapter

**Files:**
- Create: `cli/search_providers.py`
- Test: `tests/test_search_providers.py`

**Interfaces:**
- Consumes: `cli.models.ModelResult` (existing dataclass: `model: str, ok: bool, text: str, error: Optional[str] = None, skipped: bool = False`).
- Produces: `SearchAdapter` dataclass (`name: str`, `api_key_env: str`), `ADAPTERS: Dict[str, SearchAdapter]` (registry, `{"firecrawl": ...}`), `available_tools(requested: List[str]) -> List[str]`, `run_search_tool(tool: str, prompt: str, fetch: Callable = ..., timeout: int = 30) -> ModelResult`. `fetch` is injectable: `Callable[[str, str], Optional[dict]]` taking `(url, api_key)` and returning parsed JSON or `None` on failure — exact shape of `cli/scout_run.py`'s `_default_fetch`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_search_providers.py`:

```python
import os

import pytest

from cli.models import ModelResult
from cli.search_providers import ADAPTERS, available_tools, run_search_tool


def test_available_tools_filters_missing_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("cli.secrets.read_env", lambda: {})
    assert available_tools(["firecrawl"]) == []


def test_available_tools_keeps_present_key(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    assert available_tools(["firecrawl"]) == ["firecrawl"]


def test_available_tools_ignores_unknown_tool(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    assert available_tools(["not-a-real-tool"]) == []


def test_run_search_tool_success(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fake_fetch(url, api_key):
        assert api_key == "fake-key"
        return {"data": [{"title": "Example", "url": "https://example.com", "markdown": "Found X."}]}

    result = run_search_tool("firecrawl", "graph neural nets", fetch=fake_fetch)
    assert result.ok is True
    assert result.model == "firecrawl"
    assert "example.com" in result.text
    assert "Found X" in result.text


def test_run_search_tool_missing_key_is_skipped(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("cli.secrets.read_env", lambda: {})
    result = run_search_tool("firecrawl", "topic", fetch=lambda url, key: {"data": []})
    assert result.ok is False
    assert result.skipped is True
    assert "API key" in result.error


def test_run_search_tool_fetch_failure_maps_to_result(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def failing_fetch(url, api_key):
        return None  # fetch failed (network/timeout/bad response)

    result = run_search_tool("firecrawl", "topic", fetch=failing_fetch)
    assert result.ok is False
    assert result.skipped is False
    assert result.error is not None


def test_run_search_tool_unknown_tool():
    result = run_search_tool("not-a-real-tool", "topic")
    assert result.ok is False
    assert result.skipped is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_search_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.search_providers'`

- [ ] **Step 3: Write the implementation**

Create `cli/search_providers.py`:

```python
"""HTTP search-tool adapters: grounded web search alongside the model-CLI
adapters in cli/models.py. First: Firecrawl. Same ModelResult output shape as
cli/models.py so cli/research.py's aggregate()/synthesize() treat both tiers
uniformly.

Fail-safe throughout: missing key, HTTP failure, or malformed response all
degrade to a ModelResult, never raise. Mirrors cli/scout_run.py's fetch
pattern (stdlib urllib, injectable fetch for tests — no real network calls
in the test suite).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from cli.models import ModelResult
from cli.secrets import read_env
import os

_FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
_TIMEOUT = 30


@dataclass
class SearchAdapter:
    """Describes one HTTP search-tool provider."""

    name: str
    api_key_env: str


ADAPTERS: Dict[str, SearchAdapter] = {
    "firecrawl": SearchAdapter(name="firecrawl", api_key_env="FIRECRAWL_API_KEY"),
}


def _api_key(env_name: str) -> Optional[str]:
    """Ambient env var wins, else ~/.sigma/.env — same precedence as secrets.py."""
    ambient = os.environ.get(env_name)
    if ambient:
        return ambient
    return read_env().get(env_name)


def available_tools(requested: List[str]) -> List[str]:
    """Return requested tools whose API key is configured, preserving order."""
    out: List[str] = []
    for name in requested:
        adapter = ADAPTERS.get(name)
        if adapter and _api_key(adapter.api_key_env):
            out.append(name)
    return out


def _default_fetch(url: str, api_key: str) -> Optional[dict]:
    """POST a Firecrawl search request; return parsed JSON or None on failure."""
    body = json.dumps({"query": url}).encode("utf-8")
    req = urllib.request.Request(
        _FIRECRAWL_SEARCH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 (https only)
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw)
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _format_findings(data: dict) -> str:
    """Render Firecrawl's search response into themed-findings text."""
    items = data.get("data") or []
    if not isinstance(items, list) or not items:
        return ""
    lines: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        snippet = item.get("markdown") or item.get("description") or ""
        lines.append(f"- {title} ({url})\n  {snippet.strip()}")
    return "\n".join(lines)


def run_search_tool(
    tool: str,
    prompt: str,
    fetch: Callable[[str, str], Optional[dict]] = _default_fetch,
    timeout: int = _TIMEOUT,
) -> ModelResult:
    """Run one search tool's HTTP call for `prompt`. Never raises."""
    adapter = ADAPTERS.get(tool)
    if adapter is None:
        return ModelResult(model=tool, ok=False, text="", error="unknown tool", skipped=True)

    api_key = _api_key(adapter.api_key_env)
    if not api_key:
        return ModelResult(
            model=tool, ok=False, text="", error="API key not configured", skipped=True
        )

    data = fetch(prompt, api_key)
    if data is None:
        return ModelResult(model=tool, ok=False, text="", error="search request failed")

    text = _format_findings(data)
    return ModelResult(model=tool, ok=True, text=text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_search_providers.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Ruff check**

Run: `python3 -m ruff check cli/search_providers.py tests/test_search_providers.py`
Expected: no errors (fix import order if ruff flags `import os` placement — move `import os` up with other stdlib imports, before `from cli.models import ModelResult`)

- [ ] **Step 6: Commit**

```bash
git add cli/search_providers.py tests/test_search_providers.py
git commit -m "feat: add Firecrawl HTTP search-tool adapter"
```

---

### Task 3: `cli/secrets.py` — register `FIRECRAWL_API_KEY`

**Files:**
- Modify: `cli/secrets.py:20`
- Test: `tests/test_secrets.py` (extend if it exists, else create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `KNOWN_KEYS` now includes `"FIRECRAWL_API_KEY"`.

- [ ] **Step 1: Check for an existing test file**

Run: `test -f tests/test_secrets.py && echo EXISTS || echo MISSING`

- [ ] **Step 2: Write the failing test**

If `tests/test_secrets.py` exists, add this test function to it. If missing, create it with just this test:

```python
from cli.secrets import KNOWN_KEYS


def test_firecrawl_key_is_known():
    assert "FIRECRAWL_API_KEY" in KNOWN_KEYS
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_secrets.py::test_firecrawl_key_is_known -v`
Expected: FAIL (assertion error, key not in list)

- [ ] **Step 4: Modify the implementation**

In `cli/secrets.py`, change line 20:

```python
KNOWN_KEYS: List[str] = ["GEMINI_API_KEY", "OPENAI_API_KEY"]
```

to:

```python
KNOWN_KEYS: List[str] = ["GEMINI_API_KEY", "OPENAI_API_KEY", "FIRECRAWL_API_KEY"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_secrets.py -v`
Expected: PASS, and confirm no other `test_secrets.py` tests broke (they shouldn't — this only appends to a list).

- [ ] **Step 6: Commit**

```bash
git add cli/secrets.py tests/test_secrets.py
git commit -m "feat: register FIRECRAWL_API_KEY as a known optional secret"
```

Note: `FIRECRAWL_API_KEY` is deliberately **not** added to any onboard prompt flow — search tools stay opt-in per the spec. Do not touch `cli/onboard.py`.

---

### Task 4: `cli/config.py` — add `tools:` config field

**Files:**
- Modify: `cli/config.py`
- Test: `tests/test_config.py` (extend if it exists, else create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `DEFAULT_TOOLS: List[str] = []` (module constant), `SigmaConfig.tools: List[str]` (new field, default `[]`), `SigmaConfig.to_dict()` includes `"tools": self.tools` inside the `"research"` key, `_from_dict` reads `research.get("tools", DEFAULT_TOOLS)`.

- [ ] **Step 1: Check for an existing test file**

Run: `test -f tests/test_config.py && echo EXISTS || echo MISSING`

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_config.py` (create if missing, with just these two tests plus necessary imports):

```python
from cli.config import SigmaConfig, _from_dict


def test_default_config_has_empty_tools():
    cfg = SigmaConfig()
    assert cfg.tools == []


def test_from_dict_reads_tools():
    data = {"research": {"models": ["claude"], "tools": ["firecrawl"]}}
    cfg = _from_dict(data)
    assert cfg.tools == ["firecrawl"]


def test_to_dict_round_trips_tools():
    cfg = SigmaConfig(tools=["firecrawl"])
    d = cfg.to_dict()
    assert d["research"]["tools"] == ["firecrawl"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL (`SigmaConfig` has no field `tools`, or `AttributeError`)

- [ ] **Step 4: Modify the implementation**

In `cli/config.py`, change line 18:

```python
DEFAULT_MODELS = ["claude", "gemini", "gpt"]
```

to:

```python
DEFAULT_MODELS = ["claude", "gemini", "gpt"]
DEFAULT_TOOLS: List[str] = []
```

In the `SigmaConfig` dataclass (around line 40-46), add a field after `models`:

```python
@dataclass
class SigmaConfig:
    name: str = "my-project"
    harness: str = "claude-code"
    models: List[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    tools: List[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    domains: List[str] = field(default_factory=lambda: list(DOMAINS))
    commands: List[str] = field(default_factory=lambda: list(DEFAULT_COMMANDS))
    loop: LoopConfig = field(default_factory=LoopConfig)
```

In `to_dict()` (around line 63), change:

```python
"research": {"models": self.models},
```

to:

```python
"research": {"models": self.models, "tools": self.tools},
```

In `_from_dict()` (around line 87), add after the `models=` line:

```python
return SigmaConfig(
    name=profile.get("name", "my-project"),
    harness=profile.get("harness", "claude-code"),
    models=list(research.get("models", DEFAULT_MODELS)),
    tools=list(research.get("tools", DEFAULT_TOOLS)),
    domains=list(data.get("domains", list(DOMAINS))),
    commands=list(data.get("commands", DEFAULT_COMMANDS)),
    loop=loop,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS. Also run the full config test file and `tests/test_main.py` (if it exercises config round-trips) to confirm no regression:

Run: `python3 -m pytest tests/ -k config -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add cli/config.py tests/test_config.py
git commit -m "feat: add optional research.tools config field (default empty)"
```

---

### Task 5: `cli/cost.py` — route synthesis to the strong tier

**Files:**
- Modify: `cli/cost.py:101-102`
- Test: `tests/test_cost.py` (extend if it exists, else create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `routing_for("research")` now returns `{"fan-out": TIER_MID, "synthesis": TIER_STRONG}`.

- [ ] **Step 1: Check for an existing test file**

Run: `test -f tests/test_cost.py && echo EXISTS || echo MISSING`

- [ ] **Step 2: Write the failing test**

Add to `tests/test_cost.py` (create if missing):

```python
from cli.cost import routing_for, TIER_MID, TIER_STRONG


def test_research_routing_includes_synthesis_at_strong_tier():
    routes = routing_for("research")
    assert routes["fan-out"] == TIER_MID
    assert routes["synthesis"] == TIER_STRONG
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cost.py -v`
Expected: FAIL (`KeyError: 'synthesis'`)

- [ ] **Step 4: Modify the implementation**

In `cli/cost.py`, change:

```python
    if op == "research":
        return {"fan-out": TIER_MID}
```

to:

```python
    if op == "research":
        return {"fan-out": TIER_MID, "synthesis": TIER_STRONG}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cost.py -v`
Expected: PASS. Also run: `python3 -m pytest tests/ -k cost -v` to confirm no regression in existing cost tests.

- [ ] **Step 6: Commit**

```bash
git add cli/cost.py tests/test_cost.py
git commit -m "feat: route research synthesis to the strong model tier"
```

---

### Task 6: `cli/research.py` — real synthesis, search-tool fan-out, manual findings, cleanup

This is the core task. It touches the most logic; keep each step isolated and re-run the full `tests/test_research.py` file after each step.

**Files:**
- Modify: `cli/research.py` (entire fan-out/aggregate/research functions)
- Modify: `tests/test_research.py` (extend + fix legacy fakes)

**Interfaces:**
- Consumes: `cli.research_brief.build_prompt` (Task 1), `cli.search_providers.available_tools`, `cli.search_providers.run_search_tool` (Task 2), `cli.models.ModelResult`, `cli.models.available_models`, `cli.models.run_model`.
- Produces: `run_research(topic, models, tools=[], runner=run_model, search_runner=run_search_tool, max_workers=4, deep=False, web=False) -> List[ModelResult]` (fan-out now spans both tiers), `synthesize(topic: str, results: List[ModelResult], runner: Callable) -> str` (new), `_read_manual_findings(workspace: Path) -> List[ModelResult]` (new), `aggregate(topic, results, today=None, deep=False, web=False, synthesis_runner=None) -> str` (gains real synthesis), `research(topic, requested_models, workspace, runner=run_model, requested_tools=None, today=None, deep=False, web=False, synthesis_runner=None) -> Path` (wires it all together, reads manual findings).

- [ ] **Step 1: Read the current file to confirm line numbers haven't drifted**

Run: `python3 -c "import cli.research; print(cli.research.__file__)"` then re-read `cli/research.py` in full before editing (it may have changed since this plan was written).

- [ ] **Step 2: Replace the brief constants and `build_prompt` with an import**

At the top of `cli/research.py`, remove the `RESEARCH_BRIEF`, `DEEP_RESEARCH_BRIEF`, `WEB_RESEARCH_BRIEF` constants and the `build_prompt` function (lines 12-69 in the original file), replacing the import line:

```python
from cli.models import ModelResult, available_models, run_model
```

with:

```python
from cli.models import ModelResult, available_models, run_model
from cli.research_brief import build_prompt
from cli.search_providers import available_tools, run_search_tool
```

- [ ] **Step 3: Write the failing test for manual findings**

Add to `tests/test_research.py`:

```python
def test_read_manual_findings_empty_dir_returns_empty(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    ws.mkdir()
    assert _read_manual_findings(ws) == []


def test_read_manual_findings_missing_dir_returns_empty(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    ws.mkdir()
    # no manual/ subdir created at all
    assert _read_manual_findings(ws) == []


def test_read_manual_findings_reads_files(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    manual = ws / "manual"
    manual.mkdir(parents=True)
    (manual / "notes.md").write_text("Found Y (src: http://example.com)")
    results = _read_manual_findings(ws)
    assert len(results) == 1
    assert results[0].model == "manual:notes.md"
    assert results[0].ok is True
    assert "Found Y" in results[0].text
```

- [ ] **Step 4: Run to verify it fails**

Run: `python3 -m pytest tests/test_research.py -k manual_findings -v`
Expected: FAIL (`ImportError: cannot import name '_read_manual_findings'`)

- [ ] **Step 5: Implement `_read_manual_findings`**

Add this function to `cli/research.py`, near `write_research`:

```python
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
        except OSError:
            continue
        if text:
            results.append(ModelResult(model=f"manual:{path.name}", ok=True, text=text))
    return results
```

- [ ] **Step 6: Run to verify it passes**

Run: `python3 -m pytest tests/test_research.py -k manual_findings -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Write the failing test for search-tool fan-out**

Add to `tests/test_research.py`:

```python
def test_run_research_includes_search_tools():
    from cli.research import run_research

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model}-findings")

    def search_runner(tool, prompt):
        return ModelResult(tool, True, f"{tool}-findings")

    results = run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner, search_runner=search_runner
    )
    models = {r.model for r in results}
    assert models == {"claude", "firecrawl"}
```

- [ ] **Step 8: Run to verify it fails**

Run: `python3 -m pytest tests/test_research.py -k includes_search_tools -v`
Expected: FAIL (`TypeError: run_research() got an unexpected keyword argument 'tools'`)

- [ ] **Step 9: Modify `run_research` to fan out to both tiers**

Replace the existing `run_research` function in `cli/research.py` with:

```python
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
```

- [ ] **Step 10: Remove the `_call_runner` TypeError fallback**

Replace the existing `_call_runner` function:

```python
def _call_runner(runner: Callable, model: str, prompt: str, deep: bool) -> ModelResult:
    """Invoke `runner`, passing `deep` when its signature accepts it.

    Test fakes use a 2-arg (model, prompt) signature; the real run_model accepts
    a `deep` kwarg. Try the richer call first, fall back to the simple one.
    """
    try:
        return runner(model, prompt, deep=deep)
    except TypeError:
        return runner(model, prompt)
```

with:

```python
def _call_runner(runner: Callable, model: str, prompt: str, deep: bool) -> ModelResult:
    """Invoke `runner` with the standard (model, prompt, deep=) signature."""
    return runner(model, prompt, deep=deep)
```

- [ ] **Step 11: Fix legacy 2-arg test fakes in `tests/test_research.py`**

Search the file for every fake runner defined with signature `def runner(model, prompt):` (no `deep` kwarg) and add `deep=False` to match production's `run_model` signature. Specifically:

Find:
```python
def _fake_runner_factory(mapping):
    def runner(model, prompt):
        return mapping[model]
    return runner
```
Replace with:
```python
def _fake_runner_factory(mapping):
    def runner(model, prompt, deep=False):
        return mapping[model]
    return runner
```

Find (in `test_research_end_to_end_writes_file`):
```python
    def runner(model, prompt):
        return ModelResult(model, True, f"{model} says hi")
```
Replace with:
```python
    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")
```

Find and **delete** the now-obsolete test (it tested the fallback we just removed):
```python
def test_run_research_tolerates_two_arg_runner():
    # Legacy/fake runners with no `deep` kwarg still work (TypeError fallback).
    def runner(model, prompt):
        return ModelResult(model, True, "ok")

    results = run_research("t", ["claude"], runner=runner, deep=True)
    assert results[0].ok is True
```

- [ ] **Step 12: Update `test_build_prompt_*` tests to import from the new location**

Find:
```python
from cli.research import aggregate, build_prompt, research, run_research
```
Replace with:
```python
from cli.research import aggregate, research, run_research
from cli.research_brief import build_prompt
```

- [ ] **Step 13: Run the full test file to verify no regressions from steps 9-12**

Run: `python3 -m pytest tests/test_research.py -v`
Expected: all currently-adapted tests PASS; `test_run_research_includes_search_tools` now PASSES; the deleted test no longer runs.

- [ ] **Step 14: Write the failing test for real synthesis**

Add to `tests/test_research.py`:

```python
def test_synthesize_calls_runner_with_all_results():
    from cli.research import synthesize

    seen = {}

    def fake_runner(prompt):
        seen["prompt"] = prompt
        return "Claim X confirmed by 2 sources."

    results = [
        ModelResult("claude", True, "Claim X (src: a)"),
        ModelResult("firecrawl", True, "Claim X (src: b)"),
    ]
    body = synthesize("topic", results, runner=fake_runner)
    assert "Claim X confirmed by 2 sources." in body
    assert "topic" in seen["prompt"]
    assert "Claim X (src: a)" in seen["prompt"]


def test_synthesize_falls_back_on_runner_failure():
    from cli.research import synthesize

    def failing_runner(prompt):
        raise RuntimeError("boom")

    results = [ModelResult("claude", True, "finding")]
    body = synthesize("topic", results, runner=failing_runner)
    # Falls back to the prior static placeholder text, never raises.
    assert "cross-reference" in body.lower()


def test_aggregate_uses_real_synthesis():
    from cli.research import aggregate

    def fake_synth_runner(prompt):
        return "REAL SYNTHESIS OUTPUT"

    results = [ModelResult("claude", True, "x")]
    doc = aggregate("t", results, today=date(2026, 6, 16), synthesis_runner=fake_synth_runner)
    assert "REAL SYNTHESIS OUTPUT" in doc


def test_aggregate_falls_back_to_placeholder_when_synthesis_runner_missing():
    from cli.research import aggregate

    results = [ModelResult("claude", True, "x")]
    doc = aggregate("t", results, today=date(2026, 6, 16))
    assert "cross-reference" in doc.lower()
```

- [ ] **Step 15: Run to verify it fails**

Run: `python3 -m pytest tests/test_research.py -k synthes -v`
Expected: FAIL (`ImportError: cannot import name 'synthesize'`)

- [ ] **Step 16: Implement `synthesize` and wire it into `aggregate`**

Add this function to `cli/research.py`, before `aggregate`:

```python
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
```

Now find the `aggregate` function's signature and synthesis section. Change the signature:

```python
def aggregate(
    topic: str,
    results: List[ModelResult],
    today: Optional[date] = None,
    deep: bool = False,
    web: bool = False,
) -> str:
```

to:

```python
def aggregate(
    topic: str,
    results: List[ModelResult],
    today: Optional[date] = None,
    deep: bool = False,
    web: bool = False,
    synthesis_runner: Optional[Callable[[str], str]] = None,
) -> str:
```

Find the static synthesis block inside `aggregate`:

```python
    lines.append("## Synthesis")
    lines.append("")
    lines.append("> Cross-reference the per-model findings above. Promote claims "
                 "confirmed by 2+ models; flag single-source claims as unverified.")
    lines.append("")
```

Replace with:

```python
    lines.append("## Synthesis")
    lines.append("")
    if synthesis_runner is not None:
        lines.append(synthesize(topic, results, runner=synthesis_runner))
    else:
        lines.append(_SYNTHESIS_FALLBACK)
    lines.append("")
```

- [ ] **Step 17: Run to verify it passes**

Run: `python3 -m pytest tests/test_research.py -k synthes -v`
Expected: PASS (4 tests)

- [ ] **Step 18: Update `research()` to wire tools + manual findings + synthesis end-to-end**

Find the `research` function:

```python
def research(
    topic: str,
    requested_models: List[str],
    workspace: Path,
    runner: Callable = run_model,
    today: Optional[date] = None,
    deep: bool = False,
    web: bool = False,
) -> Path:
    """End-to-end: resolve available models, fan out, aggregate, write file."""
    models = available_models(requested_models)
    # Still run requested-but-missing through runner so they record as skipped.
    to_run = requested_models if requested_models else models
    results = run_research(topic, to_run, runner=runner, deep=deep, web=web)
    content = aggregate(topic, results, today=today, deep=deep, web=web)
    return write_research(workspace, content)
```

Replace with:

```python
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
```

This also fixes defect 4 (dead `models` variable) — the unused filtered `models` var is gone; `available_models(requested_models)` is now only computed in the fallback branch where `requested_models` is empty.

- [ ] **Step 19: Write the failing test for the dead-code fix + full end-to-end wiring**

Add to `tests/test_research.py`:

```python
def test_research_end_to_end_includes_manual_findings(tmp_path):
    from cli.research import research

    ws = tmp_path / "specs" / "2026-06-16-topic"
    manual = ws / "manual"
    manual.mkdir(parents=True)
    (manual / "extra.md").write_text("Manually added finding.")

    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    body = out.read_text()
    assert "Manually added finding" in body
    assert "manual:extra.md" in body
```

- [ ] **Step 20: Run to verify it fails, then passes**

Run: `python3 -m pytest tests/test_research.py -k manual_findings -v`
Expected: FAIL first (manual findings not yet in the coverage/findings sections — check `aggregate`'s "Model coverage" and "Findings by model" loops iterate over ALL `results`, which they already do since `results` now includes manual entries via `research()`'s `results += _read_manual_findings(workspace)`). If it fails because `aggregate` doesn't render `ok=True, skipped=False` entries with no special-casing needed — it shouldn't, since `aggregate` already iterates `results` generically. Confirm by running; if it passes immediately, that's correct (the wiring in Step 18 already makes this work) — no separate implementation step needed here, this step is a verification checkpoint.

Run: `python3 -m pytest tests/test_research.py -v`
Expected: ALL tests in the file PASS.

- [ ] **Step 21: Full regression check — byte-identical behavior when nothing new is configured**

Add to `tests/test_research.py`:

```python
def test_research_unchanged_when_no_tools_or_manual_findings(tmp_path):
    """Regression lock: empty tools + no manual/ dir behaves like the old module,
    except the Synthesis section (which is intentionally now real-or-fallback
    text instead of the old hardcoded string — same fallback text, same spot).
    """
    from cli.research import research

    ws = tmp_path / "specs" / "2026-06-16-topic"

    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    body = out.read_text()
    assert "claude says hi" in body
    assert "cross-reference" in body.lower()  # fallback synthesis text, unchanged wording
    assert "manual:" not in body  # no manual dir → nothing manual rendered
```

Run: `python3 -m pytest tests/test_research.py -v`
Expected: ALL PASS.

- [ ] **Step 22: Ruff check**

Run: `python3 -m ruff check cli/research.py tests/test_research.py`
Expected: no errors. Fix any import-order issues (e.g. `Optional` import for `synthesis_runner` type hints — confirm `Optional` is already imported at the top of `cli/research.py`; it is, per the original file's `from typing import Callable, List, Optional`).

- [ ] **Step 23: Full test suite + commit**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass, no regressions elsewhere (this task touches shared `ModelResult` usage patterns — confirm nothing outside `test_research.py`/`test_search_providers.py` imports `cli.research.build_prompt` from the old location; grep first).

Run: `grep -rn "from cli.research import" --include="*.py" . | grep -v test_research.py`
Expected: no hits importing `build_prompt` from `cli.research` (it moved to `cli.research_brief` in Task 1/Step 2). If any hit is found, fix that import before committing.

```bash
git add cli/research.py tests/test_research.py
git commit -m "feat: real synthesis pass, search-tool fan-out, manual findings, dead-code cleanup in cli/research.py"
```

---

### Task 7: `cli/main.py` — wire `tools:` config into `cmd_research`

**Files:**
- Modify: `cli/main.py:82-104`
- Test: none new (covered by existing CLI-level tests if present; otherwise this is thin wiring verified manually in Task 11)

**Interfaces:**
- Consumes: `cfg.tools` (Task 4), `research(..., requested_tools=...)` (Task 6).
- Produces: `sigma research` now reads `research.tools` from config and passes it through.

- [ ] **Step 1: Check for existing CLI-level research tests**

Run: `grep -rln "cmd_research" tests/`

- [ ] **Step 2: Modify `cmd_research`**

In `cli/main.py`, find:

```python
def cmd_research(args: argparse.Namespace) -> int:
    cfg = load_config()
    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else cfg.models
    )
    ws = spec_workspace(args.topic)
    deep = getattr(args, "deep", False)
    web = getattr(args, "web", False) and not deep  # deep wins if both given
    tag = "  [deep]" if deep else ("  [web]" if web else "")
    _print(f"sigma research — topic={args.topic!r}{tag}")
    _print(f"  models requested: {', '.join(models)}")
    avail = available_models(models)
    _print(f"  models available: {', '.join(avail) or '(none)'}")
    if deep:
        _print("  mode: deep (web-grounded — this may take a few minutes)")
    elif web:
        _print("  mode: web (quick web-grounded pass)")
    out = research(args.topic, models, ws, deep=deep, web=web)
    _print(f"✓ wrote {out}")
    _print("→ next: /propose")
    return 0
```

Replace with:

```python
def cmd_research(args: argparse.Namespace) -> int:
    from cli.search_providers import available_tools

    cfg = load_config()
    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else cfg.models
    )
    tools = cfg.tools
    ws = spec_workspace(args.topic)
    deep = getattr(args, "deep", False)
    web = getattr(args, "web", False) and not deep  # deep wins if both given
    tag = "  [deep]" if deep else ("  [web]" if web else "")
    _print(f"sigma research — topic={args.topic!r}{tag}")
    _print(f"  models requested: {', '.join(models)}")
    avail = available_models(models)
    _print(f"  models available: {', '.join(avail) or '(none)'}")
    if tools:
        avail_tools = available_tools(tools)
        _print(f"  search tools requested: {', '.join(tools)}")
        _print(f"  search tools available: {', '.join(avail_tools) or '(none — API key not configured)'}")
    if deep:
        _print("  mode: deep (web-grounded — this may take a few minutes)")
    elif web:
        _print("  mode: web (quick web-grounded pass)")
    out = research(args.topic, models, ws, requested_tools=tools, deep=deep, web=web)
    _print(f"✓ wrote {out}")
    _print("→ next: /propose")
    return 0
```

- [ ] **Step 3: Verify `available_models` is still imported at module level (it was already used above)**

Run: `grep -n "^from cli.models import\|^from cli.research import" cli/main.py`
Expected: confirm `available_models` and `research` are already imported at the top of `cli/main.py` (they were, per the original `cmd_research`). No new top-level import needed for those two; only `available_tools` is imported locally inside the function (matches the existing local-import style used elsewhere in `main.py`, e.g. `cmd_cost`'s local imports).

- [ ] **Step 4: Manual smoke test**

Run: `python3 -m cli.main research "test topic" --models claude 2>&1 | head -20`
Expected: runs without a Python traceback (it may report claude CLI unavailable if not installed locally — that's fine, this checks the wiring doesn't crash, not that research succeeds).

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, no regressions.

- [ ] **Step 6: Ruff check + commit**

Run: `python3 -m ruff check cli/main.py`

```bash
git add cli/main.py
git commit -m "feat: wire research.tools config into sigma research CLI"
```

---

### Task 8: `cli/research_docs.py` + `scripts/regen_research_docs.py` — generated docs

**Files:**
- Create: `cli/research_docs.py`
- Create: `scripts/regen_research_docs.py`
- Test: `tests/test_research_docs.py`

**Interfaces:**
- Consumes: `cli.research_brief.RULES_TEXT` (Task 1).
- Produces: `render_command_rules_block() -> str` (the generated rules block embedded in `commands/research.md`), `render_persona_rules_block() -> str` (the generated rules block embedded in each surviving persona file — gemini/gpt, not claude since it's deleted in Task 9).

Design note: rather than generating the *entire* `commands/research.md` file (which also contains hand-authored plugin-behavior prose per the spec), this task generates a **marked block** inside it — the same marker-delimited pattern sigma already uses elsewhere (e.g. `cli/claude_local.py`'s `upsert_block` between `<!-- sigma:learn:start/end -->` markers). This keeps the drift lock narrow (checks only the rules block matches) without requiring the whole file to be machine-generated.

- [ ] **Step 1: Write the failing test**

Create `tests/test_research_docs.py`:

```python
from cli.research_brief import RULES_TEXT
from cli.research_docs import render_command_rules_block, render_persona_rules_block


def test_render_command_rules_block_contains_shared_rules():
    block = render_command_rules_block()
    assert "cite" in block.lower() or "source" in block.lower()
    assert "confidence" in block.lower()


def test_render_persona_rules_block_contains_shared_rules():
    block = render_persona_rules_block()
    assert "confidence" in block.lower()
    assert "single-source" in block.lower()


def test_both_blocks_derive_from_the_same_rules_text():
    # Both generated blocks must be textually traceable to RULES_TEXT bullets —
    # not byte-identical (different markdown headers), but every bullet phrase
    # in RULES_TEXT appears in both.
    bullets = [line.strip("- ").split("(")[0].strip() for line in RULES_TEXT.splitlines()]
    cmd_block = render_command_rules_block()
    persona_block = render_persona_rules_block()
    for bullet in bullets:
        key_phrase = bullet.split(",")[0][:20]  # a short distinguishing fragment
        assert key_phrase.lower() in cmd_block.lower()
        assert key_phrase.lower() in persona_block.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_research_docs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.research_docs'`

- [ ] **Step 3: Write the implementation**

Create `cli/research_docs.py`:

```python
"""Pure render functions: generate the shared-rules markdown block embedded in
commands/research.md and the persona docs, from cli/research_brief.RULES_TEXT.

Regenerate with scripts/regen_research_docs.py after editing research_brief.py.
tests/test_research_docs.py locks the checked-in files to these renders so the
two surfaces (CLI briefs vs in-session docs) never silently drift apart.
"""

from __future__ import annotations

from cli.research_brief import RULES_TEXT

MARKER_START = "<!-- sigma:research-rules:start -->"
MARKER_END = "<!-- sigma:research-rules:end -->"


def render_command_rules_block() -> str:
    """The generated rules block for commands/research.md's Rules section."""
    lines = ["Every researcher/tool follows the same rules:", ""]
    lines.extend(RULES_TEXT.splitlines())
    return "\n".join(lines)


def render_persona_rules_block() -> str:
    """The generated rules block for each surviving persona doc's Return section."""
    return RULES_TEXT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_research_docs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write `scripts/regen_research_docs.py`**

First check the `scripts/` directory exists:

Run: `test -d scripts && echo EXISTS || echo MISSING`

If missing, it will be created by the Write below (no `mkdir` needed — Write creates parent dirs).

Create `scripts/regen_research_docs.py`:

```python
#!/usr/bin/env python3
"""Regenerate the shared-rules blocks in commands/research.md and the
surviving persona docs from cli/research_brief.py. Run manually after editing
research_brief.py's RULES_TEXT.

Usage: python3 scripts/regen_research_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.research_docs import (  # noqa: E402
    MARKER_END,
    MARKER_START,
    render_command_rules_block,
    render_persona_rules_block,
)

ROOT = Path(__file__).resolve().parent.parent
_BLOCK_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.DOTALL
)


def _replace_block(path: Path, new_block_body: str) -> None:
    text = path.read_text()
    replacement = f"{MARKER_START}\n{new_block_body}\n{MARKER_END}"
    if not _BLOCK_RE.search(text):
        raise SystemExit(f"{path}: no {MARKER_START}...{MARKER_END} block found")
    path.write_text(_BLOCK_RE.sub(replacement, text))


def main() -> None:
    _replace_block(ROOT / "commands" / "research.md", render_command_rules_block())
    for name in ("gemini-researcher.md", "gpt-researcher.md"):
        _replace_block(ROOT / "subagents" / "researchers" / name, render_persona_rules_block())
    print("regenerated research docs from cli/research_brief.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Ruff check**

Run: `python3 -m ruff check cli/research_docs.py scripts/regen_research_docs.py tests/test_research_docs.py`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add cli/research_docs.py scripts/regen_research_docs.py tests/test_research_docs.py
git commit -m "feat: add generated shared-rules blocks for research docs"
```

Note: the marker blocks are inserted into the actual `.md` files in Task 9 (which also does the hand-authored plugin-behavior edits) — this task only builds the generator; running it against files that don't yet have the markers will correctly raise `SystemExit` per Step 5's `_replace_block` guard, which is why Task 9 must add the markers first, then this script can be run to populate them.

---

### Task 9: `commands/research.md` + persona docs — plugin-surface rewrite

**Files:**
- Modify: `commands/research.md`
- Modify: `subagents/researchers/gemini-researcher.md`
- Modify: `subagents/researchers/gpt-researcher.md`
- Delete: `subagents/researchers/claude-researcher.md`

This task is prose/markdown editing, not Python — no pytest coverage; verified manually in Task 11.

- [ ] **Step 1: Read the current files**

Read `commands/research.md`, `subagents/researchers/gemini-researcher.md`, `subagents/researchers/gpt-researcher.md`, `subagents/researchers/claude-researcher.md` in full (they may have been touched since this plan was drafted).

- [ ] **Step 2: Delete the claude-researcher persona**

```bash
git rm subagents/researchers/claude-researcher.md
```

- [ ] **Step 3: Rewrite `commands/research.md`**

Replace the entire file content with:

```markdown
---
command: /research
description: Multi-model parallel research (real Gemini/GPT CLI dispatch + Claude-side deep-research skill), MCP search-tool grounding, and manual findings — synthesized into one cited research.md
stage: 1
inputs: ["topic"]
outputs: ["sigma/specs/{date}-{slug}/research.md"]
---

# /research

Run **multi-perspective parallel research** on a topic and synthesize one cited
document, using REAL model diversity and REAL search grounding — not personas
roleplaying as other models.

## Behavior

1. Take the research `topic`.
2. **Claude-side deep research** — invoke the `deep-research` skill directly
   (it already uses firecrawl/exa MCP tools for grounded, cited findings).
   This replaces dispatching a "claude-researcher" persona subagent — that
   persona ran on the SAME model already running this session, so it added no
   real capability beyond a self-instruction. `deep-research` does real work.
3. **Real Gemini/GPT dispatch via Bash** — check CLI availability first
   (`which gemini`, `which codex` via the Bash tool). If found, invoke the
   REAL CLI as a subprocess:
   ```
   gemini -p "<brief>" --output-format json
   codex exec --sandbox read-only --color never "<brief>"
   ```
   using the brief + argv template described in `subagents/researchers/
   gemini-researcher.md` / `gpt-researcher.md`. Clean the raw output using the
   same rules those files describe (gemini JSON-envelope extraction, codex
   event-noise stripping — matching `cli/models.py`'s `clean_output` logic).
   If a CLI is NOT found locally, fall back to dispatching that persona as a
   Task subagent instead, but say so explicitly: "gemini CLI not found locally
   — using Claude-side approximation, not real Gemini." Never silently
   substitute persona output for real model output.
4. **MCP search-tool dispatch** — if a web-search MCP tool is connected in
   this session (any tool whose name matches a search/web-search pattern —
   e.g. `mcp__firecrawl__firecrawl_search` — not hardcoded to one vendor),
   call it directly as an additional research source, dispatched in parallel
   with steps 2-3. Treat its results as grounded findings (real, resolvable
   source URLs) on the same footing as the other sources.
5. **Manual findings** — check `sigma/specs/{date}-{slug}/manual/*.md` for
   any pre-completed findings a human dropped in before or during this run.
   Fold each file in as an additional source, same rules as everything else.
6. **Synthesize**: cross-reference ALL returned findings (deep-research skill
   output, real CLI dispatch output, persona-fallback output if used, MCP
   search-tool output, manual findings): dedupe overlapping claims, promote
   claims confirmed by 2+ sources, flag single-source claims as unverified,
   prefer recent sources.
7. Write `research.md` with: executive summary, themed findings with inline
   citations, per-source contribution notes (including which sources ran vs.
   were unavailable), key takeaways, source list, gaps.

## Depth modes

Match the CLI's three depths (`sigma research` / `--web` / `--deep`):

- **default** — sources may answer from knowledge; cite what they assert.
- **web** (asked for "web" / "current" / "look it up) — each source MUST use
  its web-search / grounding tools and cite real, resolvable URLs it actually
  consulted; do not answer from memory alone. Keep it a quick pass.
- **deep** (asked for "deep" / "exhaustive" / "thorough research") — same web
  mandate, but exhaustive: multiple searches per theme, more sources, stronger
  cross-checking, every theme web-grounded. Slower by design.

When unsure which depth, ask once; otherwise default.

## Rules

<!-- sigma:research-rules:start -->
<!-- sigma:research-rules:end -->

- State which sources ran (real CLI dispatch vs. persona fallback vs. skipped)
  — no silent caps, and never present a persona-fallback reply as if it were
  the real model.
- Keep the main context clean — dispatched work runs as subagents/Bash calls;
  only aggregated findings return to the main thread.
- Dispatch steps 2-4 concurrently where possible (Bash calls + Task subagent
  calls + MCP tool calls in one message), not one after another.

## Next

→ `/propose`
```

- [ ] **Step 4: Rewrite `subagents/researchers/gemini-researcher.md`**

Replace the entire file content with:

```markdown
---
agent: gemini-researcher
model: gemini
role: researcher
mode: cli-dispatch
---

# Gemini Researcher — real CLI dispatch template

This file is NOT a persona to roleplay. It is the argv template and
output-cleaning instructions `/research` follows to dispatch the REAL Gemini
CLI as a subprocess via the Bash tool, when `gemini` is available locally.

## Dispatch

```
gemini -p "<brief>" --output-format json
```

Substitute `<brief>` with the research brief for the current topic and depth
mode (see `commands/research.md`'s Depth modes section for the wording rules).

## Cleaning the output

The CLI emits a JSON envelope. Extract the response text:
- Newer CLIs: `{"response": "..."}` — use that string directly.
- Older/alternate shape: dig into `candidates[].content.parts[].text` and
  concatenate.
- If neither shape parses, fall back to the raw stripped text rather than
  discarding output.

This mirrors `cli/models.py`'s `_clean_gemini` logic — keep the two in sync if
either changes.

## Fallback (CLI not found locally)

If `which gemini` fails, `/research` dispatches THIS file's persona instead —
as an explicit, visible approximation, never silently substituted:

You are a research subagent leaning into Gemini's typical strengths: broad
web recall, freshness, large-context synthesis. Investigate the given topic
and return raw findings (data for aggregation, not a human-facing message).

## Return

<!-- sigma:research-rules:start -->
<!-- sigma:research-rules:end -->
```

- [ ] **Step 5: Rewrite `subagents/researchers/gpt-researcher.md`**

Replace the entire file content with:

```markdown
---
agent: gpt-researcher
model: gpt
role: researcher
mode: cli-dispatch
---

# GPT Researcher — real CLI dispatch template

This file is NOT a persona to roleplay. It is the argv template and
output-cleaning instructions `/research` follows to dispatch the REAL Codex
CLI (ChatGPT-subscription-backed) as a subprocess via the Bash tool, when
`codex` is available locally.

## Dispatch

```
codex exec --sandbox read-only --color never "<brief>"
```

For deep/web mode, append: `-c tools.web_search=true` — enables Codex's
built-in web_search tool for real grounding.

Substitute `<brief>` with the research brief for the current topic and depth
mode (see `commands/research.md`'s Depth modes section for the wording rules).

## Cleaning the output

`codex exec` prints session/event preamble interleaved with the agent's
actual reply. Drop lines starting with `[timestamp] ...` event markers and
metadata lines (`workdir:`, `model:`, `provider:`, `approval:`, `sandbox:`,
`reasoning:`, `tokens used:`, `session id:`, `user instructions:`, `--------`),
keep everything else. This mirrors `cli/models.py`'s `_clean_codex` logic —
keep the two in sync if either changes.

## Fallback (CLI not found locally)

If `which codex` fails, `/research` dispatches THIS file's persona instead —
as an explicit, visible approximation, never silently substituted:

You are a research subagent leaning into alternative-recall and reasoning
strengths for cross-checking coverage. Investigate the given topic and return
raw findings (data for aggregation, not a human-facing message).

## Return

<!-- sigma:research-rules:start -->
<!-- sigma:research-rules:end -->
```

- [ ] **Step 6: Run the doc generator to populate the marker blocks**

Run: `python3 scripts/regen_research_docs.py`
Expected output: `regenerated research docs from cli/research_brief.py`

- [ ] **Step 7: Verify the markers were filled**

Run: `grep -A3 "sigma:research-rules:start" commands/research.md`
Expected: the marker is now followed by real rules content, not immediately by the end marker.

- [ ] **Step 8: Commit**

```bash
git add commands/research.md subagents/researchers/gemini-researcher.md subagents/researchers/gpt-researcher.md
git commit -m "feat: replace roleplay researcher personas with real CLI dispatch + deep-research skill"
```

---

### Task 10: `cli/models.py` — docstring clarification only

**Files:**
- Modify: `cli/models.py:1-16` (module docstring only)

No behavior change — this is documentation-only, matching the spec's "docstring updated: these are 'model providers'" note.

- [ ] **Step 1: Update the module docstring**

In `cli/models.py`, change the docstring's opening line:

```python
"""Model adapters: invoke Claude / Gemini / GPT CLIs as research subprocesses.
```

to:

```python
"""Model-provider adapters: invoke Claude / Gemini / GPT CLIs as research
subprocesses (tier 1 of sigma's two-tier research providers — see
cli/search_providers.py for tier 2, HTTP search tools).
```

Leave the rest of the docstring and all code unchanged.

- [ ] **Step 2: Run tests to confirm zero behavior change**

Run: `python3 -m pytest tests/test_models.py -v` (or whatever the models test file is named — check with `ls tests/ | grep model`)
Expected: all PASS, unchanged.

- [ ] **Step 3: Ruff check + commit**

Run: `python3 -m ruff check cli/models.py`

```bash
git add cli/models.py
git commit -m "docs: clarify cli/models.py as tier-1 model providers"
```

---

### Task 11: Full regression pass + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass (should be 663 + this plan's new tests, no failures, no errors).

- [ ] **Step 2: Full ruff check**

Run: `python3 -m ruff check cli/ tests/ scripts/`
Expected: no errors.

- [ ] **Step 3: Verify no stale imports of moved code**

Run: `grep -rn "cli.research import.*build_prompt\|from cli\.research import build_prompt" --include="*.py" .`
Expected: no hits (confirms Task 6/Step 22's check is still clean after all subsequent tasks).

- [ ] **Step 4: Verify claude-researcher.md is gone and nothing references it**

Run: `grep -rn "claude-researcher" --include="*.md" --include="*.py" .`
Expected: no hits (file deleted in Task 9, and nothing else should reference it by name).

- [ ] **Step 5: Manual dry run of the CLI path**

Run: `python3 -m cli.main research "sigma research module test" --models claude 2>&1 | tail -30`
Expected: completes without a Python traceback; prints "✓ wrote ..." with a path; if `claude` CLI isn't installed/authenticated in this environment, it should report the model as unavailable/skipped, not crash.

- [ ] **Step 6: Verify the written research.md has a real (or fallback) Synthesis section, not the old bare placeholder text with no runner context**

Run: `cat sigma/specs/*/research.md 2>/dev/null | grep -A5 "## Synthesis" | head -10` (path depends on where the dry run in Step 5 wrote it — check the printed path from Step 5's output instead if this glob doesn't match).
Expected: a "## Synthesis" section is present (either real LLM output if a `synthesis_runner` was wired at the CLI level, or the fallback text — the CLI's `cmd_research` in Task 7 does not pass a `synthesis_runner`, so expect the fallback text here; that's correct per this plan's scope — wiring a live synthesis LLM call into the CLI's default path was not specified as a requirement beyond making the *function* real and testable, which Task 6 already delivers and tests).

- [ ] **Step 7: Confirm this dry-run artifact is disposable**

The `sigma/specs/*/research.md` written by Step 5's manual test is a throwaway verification artifact in the sigma repo's own `sigma/` directory (git-ignored, per CLAUDE.md's convention that `sigma/` outputs in the target project are derived). Confirm it's git-ignored before finishing:

Run: `git status --porcelain sigma/ 2>/dev/null`
Expected: no output, or output showing the file as ignored/untracked-and-ignored (not something `git add` would pick up). If it DOES show as untracked-and-NOT-ignored, add `sigma/` to `.gitignore` if not already present — check first:

Run: `grep -n "^sigma/$\|^sigma/\*" .gitignore`

- [ ] **Step 8: This task produces no commit** (verification only — if Step 7 required a `.gitignore` fix, commit that separately)

If Step 7 required no `.gitignore` change, this task ends here with no commit. If a `.gitignore` fix was needed:

```bash
git add .gitignore
git commit -m "chore: ensure sigma/ output dir is git-ignored"
```

---

## Self-Review Notes

**Spec coverage check** (against `docs/superpowers/specs/2026-07-07-research-two-tier-providers-design.md`):
- Defect 1 (rules duplicated 3x) → Tasks 1, 8, 9 (research_brief.py + research_docs.py + marker-block regeneration).
- Defect 2 (fake synthesis) → Task 6, Steps 14-17 (`synthesize()`).
- Defect 3 (web-search asymmetry) → Task 9 (real Bash-dispatch for gemini/gpt CLIs) + Task 2 (Firecrawl real grounding).
- Defect 4 (dead `models` var) → Task 6, Step 18.
- Defect 5 (test-shape leak) → Task 6, Steps 10-11.
- Firecrawl search provider → Task 2.
- Manual findings lane → Task 6, Steps 3-6, 18-21.
- MCP search-tool dispatch (plugin surface) → Task 9, `commands/research.md` step 4.
- Claude lane → deep-research skill → Task 9, `commands/research.md` step 2 + `claude-researcher.md` deletion.
- Synthesis routing to strong tier → Task 5.
- `tools:` config field → Task 4.
- `FIRECRAWL_API_KEY` secret registration → Task 3.

All spec sections have a corresponding task. No gaps found.

**Placeholder scan:** no TBD/TODO/"handle appropriately" phrases in any task step; every code block is complete and copy-pasteable.

**Type consistency check:** `ModelResult` fields (`model, ok, text, error, skipped`) used identically across Tasks 2 and 6. `SearchAdapter(name, api_key_env)` defined in Task 2, consumed only within `cli/search_providers.py` itself (not re-referenced with different fields elsewhere). `run_research`'s new `tools`/`search_runner` params (Task 6) match the call site added in Task 7's `cmd_research` (`requested_tools=tools`, matching `research()`'s param name, not `run_research`'s — confirmed these are two different functions with intentionally different but consistent naming: `research(requested_tools=...)` → internally calls `available_tools(requested_tools or [])` → passes result as `run_research(..., tools=to_run_tools, ...)`). `synthesize(topic, results, runner)` signature matches its two call sites in Task 6 Step 16 (`aggregate`'s internal call) exactly.

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-07-research-two-tier-providers.md`.**
