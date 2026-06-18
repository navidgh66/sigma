# Design: sigma research-module upgrade + codebase-learning + caveman onboarding

*Date: 2026-06-18 · Status: approved, ready for implementation plan*

## Context

sigma's research module (`cli/models.py`, `cli/research.py`) fans a research brief
out to claude / gemini / gpt CLIs in parallel and aggregates cited findings into
`research.md`. Three problems and two additive opportunities motivate this work:

1. **The GPT adapter is dead.** `cli/models.py` shells `openai api chat.completions.create`
   — the pre-1.0 OpenAI CLI command, removed from the modern `openai` package. It
   cannot run.
2. **No subscription-backed path for GPT.** The OpenAI SDK Responses API needs a
   paid API key (per-call credit). The user has a ChatGPT subscription and wants to
   use it. The **Codex CLI** (`codex exec`) authenticates with the ChatGPT login
   (verified locally: `auth mode chatgpt`, `stored API key false`) — subscription-backed,
   zero API credit.
3. **No live web research.** All models answer from memory. A `--deep` mode should
   enable web search / grounding so findings cite live sources.
4. **No codebase-learning artifact.** Bundle a command that learns a codebase and
   persists durable, editor-playable artifacts (CodeTour + architecture map).
5. **Caveman onboarding.** Wire the caveman session-start hook into `sigma onboard`,
   RTK-style (confirm-gated).

Research backing these decisions (cited): OpenAI Responses/Codex CLI docs, Gemini
CLI + grounding docs, Corti "Graphify" article, Microsoft CodeTour, aider repo-map.
The Python 3.10+ floor of Graphify and the maintained tree-sitter stack is why
Section C generates artifacts via Claude rather than bundling a graph engine.

## Constraints (unchanged project invariants)

- **Python 3.9 target.** Type hints use `Optional[X]` / `List[X]` from `typing`.
- **Dependency-light.** stdlib + `pyyaml` + `rich` only. No new runtime deps.
- **argv, never shell** for all model/agent invocation (no injection risk).
- **Pure logic separated from subprocess execution** — everything testable with fakes.
- **232 pytest tests stay green**; ruff clean. Each section adds coverage.
- **Confirm-gated** anything touching global `~/.claude/settings.json`.

---

## Section A — Fix the broken model invocations

**Scope:** `cli/models.py` only (plus its tests).

Replace the dead `gpt` adapter and upgrade `gemini` to structured output. Add an
output-cleaning step so aggregation receives plain text, not CLI event noise.

### Adapter registry changes

```python
"gpt": ModelAdapter(
    name="gpt",
    executable="codex",
    arg_template=["{exe}", "exec", "--sandbox", "read-only",
                  "--color", "never", "{prompt}"],
),
"gemini": ModelAdapter(
    name="gemini",
    executable="gemini",
    arg_template=["{exe}", "-p", "{prompt}", "--output-format", "json"],
),
# claude unchanged: ["{exe}", "-p", "{prompt}"]
```

- `codex exec` runs non-interactively, prompt via argv, `--sandbox read-only` (safe
  for research — model cannot edit files), `--color never` (clean stdout).
- `gemini --output-format json` gives parseable output instead of scraped stdout.

### Output cleaning

New pure function `clean_output(model: str, raw: str) -> str` in `models.py`:
- `gemini`: parse JSON, extract the response text field; fall back to raw on parse
  failure (never crash the fan-out).
- `gpt` (codex): strip the event/preamble lines codex emits, keep the final message.
- `claude`: passthrough.

`run_model` applies `clean_output` to `proc.stdout` before returning `ModelResult.text`.

### Graceful degradation

`available_models` already skips CLIs that `shutil.which` can't find. gemini is not
installed locally → it records as skipped, fan-out continues. No code change needed;
onboard/doctor surface the gap (Section D wiring + existing model checks).

---

## Section B — `--deep` web-grounded research mode

**Scope:** `cli/models.py`, `cli/research.py`, `cli/main.py` (flag), tests.

A `--deep` flag on `sigma research` enables web search / grounding across all three
CLIs. Same fan-out + aggregate; web-enabled + longer timeout.

| Model  | quick (default)     | `--deep`                                    |
|--------|---------------------|---------------------------------------------|
| codex  | `exec` plain        | append `-c tools.web_search=true`           |
| gemini | `-p ... --json`     | grounding (Google Search) enabled           |
| claude | `-p`                | `-p` + web-search instruction in the brief  |

### Implementation

- `ModelAdapter` gains `deep_args: List[str] = field(default_factory=list)`,
  appended to the argv only when `deep=True`. (codex: `["-c", "tools.web_search=true"]`;
  gemini: grounding flag per CLI version; claude: none — handled via brief.)
- `build_argv(prompt, deep=False)` appends `deep_args` when deep.
- `run_model(..., deep=False)` and `run_research(..., deep=False)` thread the flag.
- Timeout: default 300s → **900s** when deep (web research is slow).
- `research.py`: a `DEEP_RESEARCH_BRIEF` variant demanding live citations; `build_prompt(topic, deep=False)` selects it.
- `aggregate()` header notes the mode (`Mode: deep (web-grounded)` vs `Mode: quick`),
  keeping the existing no-silent-caps model-coverage table.
- `main.py`: `sigma research "topic" --deep` (argparse `--deep` store_true), threaded
  to `research(...)`.

---

## Section C — `sigma learn` (codebase-learning command)

**Scope:** new `cli/learn.py`, new `cli/codetour.py`, vendored skills, `cli/main.py`,
`commands/learn.md`, tests.

Produce two durable artifacts via the existing AgentRunner driving Claude — **no
graph engine** (Graphify and the maintained tree-sitter stack require Python 3.10+,
which conflicts with the 3.9 floor).

### Artifacts

1. **`.tours/<slug>.tour`** — CodeTour JSON walkthrough (persona-targeted, anchored
   to real files/lines). Editor-playable (VS Code / IntelliJ CodeTour).
2. **`ARCHITECTURE.md`** — architecture map / onboarding doc (CLAUDE.md-style).

### `cli/codetour.py` — pure validator (~50 lines)

`validate_tour(data: dict, repo_root: Path) -> List[str]` returns a list of problems
(empty = valid):
- `title` present and non-empty; `steps` is a non-empty list.
- Each step has a `description`; if it has `file`, the file exists under `repo_root`.
- If a step has `line`, it is 1-based and within the file's line count.
- If a step has `pattern`, the pattern occurs in the file.

Pure logic, no I/O beyond reading the anchored files — testable with a fake repo tree.

### `cli/learn.py` — orchestration

`run_learn(topic, runner, workspace, vendor, persona=None, dry_run=False)`:
1. Build a learn prompt (what to map, persona, output contract for both artifacts).
2. Inject the bundled `code-tour` + `codebase-onboarding` skill bodies via
   `skill_map` (extend `STAGE_SKILLS` with a `learn` entry, or a dedicated injector).
3. Drive the AgentRunner (the single execution chokepoint — injectable for tests).
4. Parse the agent's output into the two artifacts; validate the `.tour` with
   `codetour.validate_tour`; write `ARCHITECTURE.md` and `.tours/<slug>.tour`.
5. `--dry-run` prints the invocation without running the agent (mirrors stage dry-run).

### Vendored skills

Vendor `code-tour` and `codebase-onboarding` SKILL.md bodies into `skills/vendor/`
(both already installed on the machine). Wire through the existing `skill_map`
mechanism so they also work standalone in Claude Code.

### CLI + slash command

- `sigma learn` (optional `--topic`, `--persona`, `--dry-run`).
- `commands/learn.md` slash template, mirroring the other stage templates.

### Recommend-only graph tools

`sigma doctor` gains a **pure probe** that suggests **Graphify** (`graphifyy`,
MIT, Python 3.10+) and **codebase-memory-mcp** (MIT, static binary) as optional
external installs for users who want a true code knowledge graph. Cite, do not
bundle, do not auto-install (no fix-by-default).

---

## Section D — Caveman into onboarding

**Scope:** new `cli/caveman.py` (mirrors `cli/rtk.py`), `cli/onboard.py`,
`cli/checks.py`, `cli/doctor.py`, tests.

Caveman is a Claude Code plugin + one SessionStart hook in `~/.claude/settings.json`
that injects the caveman terse-output skill. This is structurally identical to RTK
(confirm-gated, idempotent, touches global shared state).

### `cli/caveman.py` — RTK-shaped

- `caveman_status(which, run, settings_path) -> Dict` → `{installed, hook_active}`.
  `hook_active` scans `settings.json` hooks for the caveman activate script (like
  `rtk._hook_active`). `installed` checks the plugin/marketplace presence.
- `install_caveman(...)` — install the caveman plugin (marketplace add + install).
- `activate_caveman(...)` — register the SessionStart hook.
- `setup_caveman(status_fn, confirm, ...)` — confirm-gated, idempotent. No-op when
  already active; confirm before anything touches global settings.

All spawning/lookups injectable — tests never install or modify real settings.

### Wiring

- `onboard.py`: a new step after the RTK step calls `setup_caveman(confirm=...)`.
- `checks.py`: a pure caveman probe (`Check`, never prints/mutates).
- `doctor.py`: surface the caveman check; offer the confirm-gated fix.

---

## Cross-cutting

- **Testing:** every pure unit (adapter build, `clean_output`, `validate_tour`,
  `caveman_status`, deep-arg threading) tested with fakes. Extend `test_e2e.py` for
  the research `--deep` flow and the `sigma learn` flow (fake runner). Keep all
  existing tests green; net test count rises.
- **3.9 hints / ruff clean** throughout.
- **Docs:** update `CLAUDE.md` (commands list, layout: `cli/learn.py`, `cli/codetour.py`,
  `cli/caveman.py`), `docs/PLAYGROUND.md`, and add `commands/learn.md`.

## Build order (sections are independent)

1. **A** — adapter fix + `clean_output` (foundation; unblocks live research).
2. **B** — `--deep` mode (builds on A's adapters).
3. **D** — caveman onboarding (independent; RTK clone, low risk).
4. **C** — `sigma learn` (largest; new command + validator + vendored skills).

## Out of scope (YAGNI)

- OpenAI Deep Research API (`o3-deep-research`) — API-key/paid only; `codex exec` +
  web search is the subscription-backed equivalent.
- Bundling a graph engine / tree-sitter (3.10+ conflict) — recommend external tools.
- google-genai / openai SDK adapters — subprocess-to-CLI keeps it subscription-backed
  and dependency-light. Revisit only if the user opts into paid API.
