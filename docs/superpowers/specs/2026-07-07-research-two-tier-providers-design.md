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

### Plugin surface — MCP search tools (zero new code)

The CLI needs `cli/search_providers.py` because a bare subprocess has no MCP
layer. The in-session `/research` command doesn't: a Claude Code session may
already have web-search MCP tools connected (Firecrawl, Exa, Tavily, or others,
depending on what the user's session has configured) — the agent calls them
directly, no subprocess, no urllib, no new adapter code.

`commands/research.md`'s Behavior section gains one new dispatch step,
alongside the existing subagent dispatch:

> If a web-search MCP tool is connected in this session (any tool whose name
> matches a search/web-search pattern — e.g. `mcp__firecrawl__firecrawl_search`
> — not hardcoded to one vendor), call it directly as an additional research
> source, dispatched in parallel with the researcher subagents. Treat its
> results as grounded findings (real, resolvable source URLs) on the same
> footing as subagent findings. State which MCP tools ran or were unavailable
> — no silent caps, same transparency rule already applied to subagent
> dispatch.

Because the instruction names a pattern ("any connected web-search MCP tool"),
not a specific vendor, Exa/Tavily/Perplexity/whatever a future session has
connected all work the same way with zero command-doc edits — this is the
plugin-side answer to "several different tools," matching the CLI side's
`SearchAdapter` extensibility without needing a CLI-side adapter for each.

**Scope of the doc-gen drift lock:** this MCP-dispatch step is plugin-specific
behavior — it doesn't apply to the CLI path (which has its own explicit
`search_providers.py` mechanism) and isn't derived from `research_brief.py`'s
shared citation/confidence/freshness rules. `commands/research.md` therefore
has two kinds of content: a generated shared-rules block (from
`research_brief.py`, checked by `tests/test_research_docs.py`) and a
hand-authored plugin-behavior block (subagent + MCP dispatch steps, NOT
generated, NOT covered by the drift-lock test). The synthesis-pass problem
(defect 2) doesn't need a plugin-side fix — a live agent already cross-
references findings organically in-session; only the CLI path's static
placeholder needed the real `synthesize()` call.

### Plugin surface — the claude researcher lane is roleplay, drop it

`subagents/researchers/claude-researcher.md` is dispatched as a Claude Code
Task subagent — which runs on the SAME model already running the session.
There is no separate "claude CLI" being invoked in-session (that only happens
on the CLI path, via `claude -p` subprocess). So today's in-session claude lane
is a subagent told to lean into "deep reasoning, code-aware synthesis" — a
persona wrapped around the same model, not a distinct capability.

For genuine Claude-side deep research, sigma already has a real tool:
`skills/deep-research` (per its description: multi-source research using
firecrawl + exa MCPs, synthesized cited reports). `commands/research.md`'s
claude lane changes from "dispatch claude-researcher subagent" to "invoke the
`deep-research` skill directly" — real firecrawl/exa-backed grounding instead
of a persona instructing itself to behave a certain way.

`subagents/researchers/claude-researcher.md` is removed;
`skills/sigma-domains`-style skill invocation replaces it in
`commands/research.md`'s Behavior section.

### Plugin surface — real Gemini/GPT dispatch via Bash, not roleplay

The same roleplay problem applies to `gemini-researcher.md` and
`gpt-researcher.md`: dispatched as Task subagents, they also run on Claude's
model — "lean into broad web recall" is an instruction, not a mechanism. A user
with real Gemini/ChatGPT subscriptions gets zero actual model diversity from
this path today; every researcher is Claude in a different costume.

Fix: `/research`'s Behavior section adds an explicit Bash-tool dispatch step
for these two lanes, reusing the exact argv `cli/models.py`'s `ADAPTERS`
already define — the in-session agent runs the real CLI as a subprocess via
the Bash tool, the same way `sigma research` does via Python's
`subprocess.run`, just invoked from the agent side instead:

```
gemini -p "<brief>" --output-format json
codex exec --sandbox read-only --color never "<brief>"
```

This requires the CLIs to be installed and authenticated locally (same
precondition `cli/models.py.available()` checks) — `/research` first checks
availability (`which gemini`, `which codex` via Bash) and, if absent, falls
back to the persona-subagent dispatch with an explicit note ("gemini CLI not
found locally — using Claude-side approximation, not real Gemini") so the
degradation is visible, never silent.

`gemini-researcher.md` / `gpt-researcher.md` are repurposed: instead of chat
personas to roleplay, their body becomes the argv template + brief-injection
instructions the agent follows to build the real Bash command. Output (raw CLI
stdout) gets cleaned using the same rules as `cli/models.py`'s `clean_output`
(gemini JSON-envelope extraction, codex event-noise stripping) — described in
prose in the persona doc since the in-session agent has no direct import of
`cli/models.py`, but referencing it as the canonical cleaning logic so the two
surfaces don't silently diverge on how they parse the same CLI output.

### Manual research input lane

New: a human (or an earlier, unrelated session) can drop raw findings as
markdown into `sigma/specs/{date}-{slug}/manual/*.md` before or during a
research run. `/research`'s Behavior section adds a step: check that directory
for files; treat each one as a pre-completed source — `ModelResult(model=
f"manual:{filename}", ok=True, text=<file content>)` — folded into the same
combine/cross-reference step as CLI-dispatched, MCP-search, and real-model
findings. No new format required beyond "themed findings with source URLs,
same rules as everything else" (from `research_brief.py`) — unstructured prose
is still accepted (folded in as unstructured context) but won't get the same
"confirmed by 2+ sources" promotion in synthesis unless it cites URLs like the
other lanes.

On the CLI path, `cli/research.py`'s `research()` gains an equivalent read
step: `_read_manual_findings(workspace)` globs `workspace/manual/*.md`, wraps
each into a `ModelResult`, and includes them in the list passed to `aggregate`
+ `synthesize` — same mechanism, no MCP/agent dependency, so the manual lane
works identically on both surfaces.

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
  remaining `subagents/researchers/<name>.md` body from `research_brief.py` /
  `research_docs.py` and asserts it matches the checked-in file content — the
  drift lock for defect 1.
- `tests/test_research.py` (extended further): `_read_manual_findings` reads
  `workspace/manual/*.md` into `ModelResult`s (fixture dir with 0/1/N files);
  manual results flow into `aggregate`/`synthesize` alongside CLI results;
  missing `manual/` dir → empty list, never an error (fail-safe, matches every
  other optional-input convention in this module).
- No automated test for the in-session Bash-dispatch or `deep-research`-skill
  behavior changes to `commands/research.md` — those are prose instructions to
  an agent, not Python; verified by manual dry-run (`sigma research --deep`
  equivalent invoked in-session) during rollout, per the "Manual verification"
  rollout step below.

## Rollout

1. `cli/research_brief.py` + `cli/research_docs.py` + `scripts/regen_research_docs.py`
   land first; regenerate `commands/research.md` + persona docs from them
   (content-preserving — same rules, now generated).
2. `cli/search_providers.py` + Firecrawl adapter + config `tools:` key.
3. `cli/research.py` synthesis pass + fan-out extension + `_read_manual_findings`.
4. `commands/research.md` + persona docs updated: claude lane → `deep-research`
   skill invocation; gemini/gpt lanes → real Bash-tool CLI dispatch (with
   availability check + visible fallback); MCP search-tool dispatch step;
   manual-findings-directory check step. `claude-researcher.md` removed.
5. Cleanup of defects 4 & 5.
6. Full test suite green, ruff clean.
7. Manual verification: run `/research` in-session on a real topic, confirm
   gemini/codex CLIs actually get invoked (visible in Bash tool calls, not
   just described), confirm manual findings in `manual/*.md` get folded in,
   confirm the claude lane produces a `deep-research`-skill-shaped report
   rather than a subagent persona reply.

## Open questions / risks

- Firecrawl API pricing/quota is out of scope for this design — the adapter is
  opt-in and skipped gracefully with no key, so it never blocks users who don't
  pay for it.
- Exa/Tavily/Perplexity Sonar are explicitly NOT built in this pass (non-goal:
  no plugin framework) — `cli/search_providers.py`'s `SearchAdapter` dataclass
  shape is intentionally simple enough that adding one later is a small, not
  architectural, change, but that's a future decision, not scope creep now.
- Gateway adapters (OpenRouter/LiteLLM — one HTTP adapter, many models via one
  paid API key) were considered and explicitly deferred: the user has real
  Gemini/GPT subscriptions already, so real CLI dispatch (this spec) gets
  genuine model diversity without introducing a pay-per-token dependency that
  would break sigma's "subscription-backed, no API credit" principle for the
  model lanes. Revisit only if subscription CLI dispatch proves insufficient.
- The Bash-tool dispatch step for gemini/gpt depends on those CLIs being
  installed + authenticated in whatever environment the in-session agent runs
  in — if a session runs somewhere without local CLI access (e.g. a sandboxed
  remote agent), the visible fallback-to-persona note is the safety valve, not
  a silent degrade.
