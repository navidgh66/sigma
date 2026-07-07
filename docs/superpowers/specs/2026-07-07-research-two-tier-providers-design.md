---
title: Research module — two-tier providers (model CLIs + search tools), real synthesis, doc-sync
date: 2026-07-07
status: approved
---

# Research module redesign: two-tier providers

## Problem

`cli/research.py` + `cli/models.py` (the `sigma research` CLI path) and the
in-session `/research` command + `subagents/researchers/*.md` (Claude Code
path) implement the same research contract twice, with five concrete defects:

1. **Rules duplicated 3x** — citation/confidence/freshness rules are hand-copied
   across the CLI brief strings (`cli/research.py`), `commands/research.md`, and
   3 persona files (`subagents/researchers/*.md`). Editing one and forgetting
   the others silently drifts the contract.
2. **`aggregate()` doesn't aggregate** — the CLI path's "Synthesis" section is a
   static string telling a future human to "cross-reference the findings above."
   No actual synthesis happens. CLAUDE.md's "aggregated, cited" claim is true for
   the in-session command (a live LLM does the cross-referencing) but false for
   the CLI.
3. **Web-search grounding is asymmetric** — only the `gpt`/`codex` adapter has a
   real `deep_args` flag (`tools.web_search=true`) forcing live search. `claude`
   and `gemini` adapters have `deep_args=[]`; their "deep"/"web" mode is prompt
   instruction only ("please search the web"), with no verified mechanism.
4. **Dead code** — `research()` computes a filtered `models` var that's unused
   whenever `requested_models` is non-empty (the common case).
5. **Test-shape leak** — `_call_runner`'s `try/except TypeError` fallback exists
   only to support legacy 2-arg test fakes; real `run_model` always accepts
   `deep=`.

Additionally, the user's actual goal is broader than fixing bugs: **do deep
research across several different models AND tools** — not just 3 chat-CLI
subprocesses. 2026 web research shows Firecrawl, Exa, Tavily, and Perplexity
Sonar as the leading AI-native search APIs; all are HTTP/API-key based, not
subscription CLIs, so they don't fit today's `ADAPTERS` (subprocess-argv) shape
without a new provider kind.

## Goals

- Fix defects 1–5 above.
- Add a working, grounded search-tool integration (Firecrawl first) alongside
  the existing model-CLI adapters, opt-in via API key (never required).
- Make the CLI path's synthesis real — an actual cross-referencing LLM call,
  not a placeholder.
- Close the doc-drift gap with a test-enforced invariant, not a comment.
- Preserve existing behavior when no tools/keys are configured (regression-safe
  — `sigma research` with zero search providers must produce byte-identical
  output to today, modulo the real synthesis section explicitly replacing the
  placeholder).

## Non-goals

- No generalized plugin/provider framework (config-driven `Provider` protocol
  for arbitrary future tools). YAGNI per CLAUDE.md's stated philosophy — build
  for the tools in front of us (3 model CLIs + Firecrawl), not speculative ones.
- No new runtime pip dependency. Firecrawl's HTTP calls use stdlib `urllib`,
  the same pattern `cli/scout_run.py` already uses for skillsmp.com. Sigma's
  runtime stays `pyyaml` + `rich` only.
- No change to the in-session `/research` command's subagent-dispatch mechanism
  (Task tool fan-out) — only its prompt *content* is now sourced from the shared
  brief via generated docs.

## Design

### Architecture

```
cli/research_brief.py    NEW — canonical rules + brief templates (quick/web/deep).
                          Single source of truth for citation/confidence/freshness
                          language. Imported by cli/research.py.

cli/research_docs.py     NEW — pure render functions that interpolate
                          research_brief.py constants into the markdown BODY
                          text used by commands/research.md and each
                          subagents/researchers/<name>.md. Frontmatter (agent
                          name, role, per-persona "strengths to lean on") stays
                          hand-authored — it's identity, not shared rules.

scripts/regen_research_docs.py  NEW — thin: calls research_docs.render_*(),
                          writes the .md files. Run manually after editing
                          research_brief.py.

tests/test_research_docs.py     NEW — drift lock: reads the checked-in .md
                          files, asserts their rules-body matches
                          render_*() output. Fails the moment brief.py and the
                          .md docs disagree.

cli/models.py             UNCHANGED shape (subprocess argv, claude/gemini/gpt).
                          Docstring updated: these are "model providers".

cli/search_providers.py  NEW — HTTP search-tool adapters. First: Firecrawl.
                          Returns ModelResult-shaped output (model=tool name,
                          ok, text, error, skipped) so aggregate() treats model
                          providers and search providers uniformly.

cli/research.py          MODIFIED — run_research fans out to BOTH model
                          providers (existing subprocess ThreadPoolExecutor)
                          and search providers (new HTTP pool) in parallel.
                          aggregate() gains a real synthesis step.
```

### Data flow

```
sigma research "topic" [--web|--deep] [--tools firecrawl]
  → research(topic, requested_models, requested_tools, workspace)
      → run_research:
          - model providers: existing subprocess pool (claude/gemini/gpt)
          - search providers: new HTTP pool (firecrawl, ...)
          both produce ModelResult; combined list preserves existing
          coverage-table shape (now spans both kinds)
      → synthesize(topic, results, runner=...) — ONE distinct LLM call
        (not one of the researchers) that cross-references all raw findings:
        promotes claims seen 2+ times, flags single-source claims, writes the
        real "## Synthesis" body.
      → aggregate() assembles: coverage table, per-provider findings, the
        REAL synthesis section, source list, next-step pointer.
      → write_research(workspace, content)
```

### Config

```yaml
research:
  models: [claude, gemini, gpt]   # existing, unchanged, DEFAULT_MODELS
  tools: [firecrawl]              # NEW, optional, DEFAULT_TOOLS = []
```

Empty `tools: []` (the default) → today's exact behavior for the provider
fan-out step. `available_tools()` mirrors `available_models()`: keeps only
tools whose API key is present (env var or `~/.sigma/.env` via
`cli/secrets.py` — same optional, never-prompted-in-onboard pattern as
`SKILLSMP_API_KEY`).

### Search provider adapter shape

```python
# cli/search_providers.py
@dataclass
class SearchAdapter:
    name: str
    api_key_env: str                                   # e.g. "FIRECRAWL_API_KEY"
    search_fn: Callable[[str, str], ModelResult]        # (topic, api_key) -> ModelResult

def available_tools(requested: List[str]) -> List[str]:
    """Like available_models: keep only tools whose API key is configured."""

def run_search_tool(tool: str, prompt: str, timeout: int = QUICK_TIMEOUT) -> ModelResult:
    """Resolve the adapter, check the key, call search_fn, wrap errors into
    ModelResult (never raises) — same fail-safe contract as run_model."""
```

Firecrawl's `search_fn` calls the Firecrawl search HTTP endpoint via stdlib
`urllib.request` (no new dependency), parses the JSON response into themed
findings with source URLs — genuinely grounded, unlike the claude/gemini
prompt-only "deep" mode.

### Synthesis pass

```python
# cli/research.py
def synthesize(topic: str, results: List[ModelResult], runner: Callable) -> str:
    """One distinct LLM call over all raw findings (model + search providers).
    Cross-references claims: 2+ providers agreeing → promoted; single-source →
    flagged unverified. Returns the real Synthesis section body.

    On failure (runner raises / times out): caller falls back to today's
    static placeholder text — degrade, never crash the whole doc.
    """
```

Distinctness: when `runner` is an object with identity (e.g. an `AgentRunner`
instance, as `loop`/`review` use), the synthesis runner must not be the same
instance as any researcher runner — same `is`-identity guard pattern as
maker≠checker. For the CLI's default bare-function `runner: Callable`, there
is no meaningful identity to check; this guard is a note for callers that pass
object-shaped runners, not a hard invariant enforced at the plain-function
call site.

### Error handling (fail-safe, matches existing module conventions)

- Missing/invalid Firecrawl key → filtered out by `available_tools`;
  `ModelResult(skipped=True, error="API key not configured")` — same shape as
  a missing model CLI.
- HTTP failure (timeout/5xx/network) → caught, `ModelResult(ok=False,
  error=str(e))` — same as a subprocess non-zero exit today.
- Synthesis call fails → `aggregate()` falls back to the current static
  placeholder rather than blocking the doc. Per-provider raw findings still
  ship.
- All providers skipped/failed across both tiers → existing "⚠️ No models
  produced findings" branch, message extended to mention tools too.

### Cleanup (defects 4 & 5)

- Remove the unused filtered `models` variable in `research()`.
- Remove `_call_runner`'s `TypeError` fallback; update
  `tests/test_research.py`'s legacy 2-arg fakes to accept `deep=False` like
  real `run_model` — the test doubles match production signature instead of
  production code bending to accommodate the doubles.

## Testing

- `tests/test_search_providers.py` (new): `available_tools` filtering
  (present/absent key), Firecrawl adapter with an injected fake HTTP call (no
  real network), error/timeout mapping to `ModelResult`.
- `tests/test_research.py` (extended): fan-out covers both provider kinds
  (assert both appear in combined results, order-independent); synthesis called
  once with all raw results via a fake runner, output lands in "## Synthesis";
  synthesis-failure fallback path (fake runner raises → doc still written with
  placeholder, no crash); regression lock — `tools=[]` config produces output
  identical to pre-change shape aside from the now-real synthesis section.
- `tests/test_research_docs.py` (new): renders `commands/research.md` and each
  `subagents/researchers/<name>.md` body from `research_brief.py` /
  `research_docs.py` and asserts it matches the checked-in file content — the
  drift lock for defect 1.

## Rollout

1. `cli/research_brief.py` + `cli/research_docs.py` + `scripts/regen_research_docs.py`
   land first; regenerate `commands/research.md` + persona docs from them
   (content-preserving — same rules, now generated).
2. `cli/search_providers.py` + Firecrawl adapter + config `tools:` key.
3. `cli/research.py` synthesis pass + fan-out extension.
4. Cleanup of defects 4 & 5.
5. Full test suite green, ruff clean.

## Open questions / risks

- Firecrawl API pricing/quota is out of scope for this design — the adapter is
  opt-in and skipped gracefully with no key, so it never blocks users who don't
  pay for it.
- Exa/Tavily/Perplexity Sonar are explicitly NOT built in this pass (non-goal:
  no plugin framework) — `cli/search_providers.py`'s `SearchAdapter` dataclass
  shape is intentionally simple enough that adding one later is a small, not
  architectural, change, but that's a future decision, not scope creep now.
