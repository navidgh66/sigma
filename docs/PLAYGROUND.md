# sigma Playground & Guide

A hands-on tour of **every** sigma feature, with copy-paste examples and what to
expect. Work top to bottom for a full walkthrough, or jump to a section.

> Convention: `$` lines are shell commands. `→` lines describe the result.
> A "topic" is any string; sigma slugifies it into a dated workspace under
> `sigma/specs/{YYYY-MM-DD}-{slug}/`.

---

## 0. Setup

```bash
# global install (one-liner)
$ curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
$ export PATH="$PATH:$HOME/.local/bin"
$ sigma --help
→ usage: sigma [-h] [--version] {init,research,propose,blueprint,spec,tasks,
  implement-task,verify,loop,hermes,board,launch}

# from a clone, without installing:
$ python3 -m cli.main --help

# dev checks (must stay green)
$ python3 -m pytest tests/ -q          # 924 passed
$ python3 -m ruff check cli/ tests/    # All checks passed!
```

### Or install as a Claude Code plugin (slash commands + skills)

```
/plugin marketplace add navidgh66/sigma     # or a local clone path
/plugin install sigma@sigma
```

→ **sigma is plugin-first.** Every stage is a native slash command — `/research
/propose /blueprint /spec /tasks /implement-task /verify /loop /hermes /board
/weave /sigma-learn-lesson` — and `sigma-present`, `sigma-domains`, `sigma-lessons`
are native skills. The pipeline **stages run in-session** (they load the domain
context-engine and are steerable).
The `sigma` CLI keeps only what Claude Code can't do in-session: parallel
`research`, the autonomous escape hatch (`loop`/`hermes`), `board`/`weave`, and
setup. The per-stage CLI wrappers were retired.

---

## 1. `sigma init` — scaffold a project

Pick the domains a project needs; writes `sigma.config.yml`.

```bash
$ sigma init --name churn-model --domains classic-ml,data-analysis
→ ✓ wrote /path/sigma.config.yml
    domains: classic-ml, data-analysis
    models:  claude, gemini, gpt

$ sigma init --domains nlp,rl           # name defaults to cwd
$ sigma init --force                    # overwrite existing config
$ sigma init --domains bogus            # ✗ unknown domain(s): bogus  (lists valid)
```

The 9 valid domains: `classic-ml deep-learning nlp rl data-analysis
data-engineering ai-agent-engineering mlops llm-engineering`.

Local override: drop a `sigma.config.local.yml` next to it — deep-merged on load
(git-ignore it for machine-specific tweaks).

---

## 2. The pipeline (8 stages)

```
research → propose → blueprint → spec → tasks → implement-task → verify → loop
```

Each stage reads the **prior** stage's artifact as context and writes its own.
Run a stage **in-session** as a slash command (`/spec`, `/tasks`, …) — it loads
the matching domain context-engine via the `sigma-domains` skill. (`sigma
research` stays a CLI command for real parallel fan-out; `sigma loop`/`hermes`
drive stages autonomously from the CLI.)

### 2a. `sigma research` — multi-model, cited

Fans out to Claude + Gemini + GPT in parallel (whichever CLIs are installed),
aggregates + dedupes + cites into `research.md`.

```bash
$ sigma research "active learning for imbalanced fraud labels"
→ sigma research — topic='active learning for imbalanced fraud labels'
    models requested: claude, gemini, gpt
    models available: claude            # gemini/gpt skipped if CLI absent
  ✓ wrote sigma/specs/2026-06-17-active-learning-for-imbalanced-fraud-labels/research.md
  → next: /propose

$ sigma research "topic" --models claude,gemini   # restrict models
$ sigma research "topic" --web                     # quick web-grounded pass
$ sigma research "topic" --deep                    # exhaustive web research (slower, 900s)
```

→ Missing model CLIs degrade gracefully (skipped, not an error). Every claim in
`research.md` is cited; fact and inference are separated.

**Three depths:** plain (from memory, fast), `--web` (quick live web search,
lighter brief), `--deep` (exhaustive web research, long timeout). `--deep` wins if
both `--web` and `--deep` are given. The header marks the mode used.

### 2b. Stages propose → verify (in-session slash commands)

These run **inside Claude Code** as slash commands — each reads the prior
artifact and loads the right domain context-engine (`sigma-domains` skill):

```
/propose          # research.md   → proposals.md
/blueprint        # proposals.md  → architecture.md
/spec             # architecture.md → spec.md
/tasks            # spec.md → tasks.md  (domain-routed checklist)
/implement-task   # tasks.md → impl/
/verify           # spec.md (+ full chain via chain.json) → verify/
```

Run them in the session for the topic's workspace. To drive the same stages
**autonomously** from the terminal, use `sigma hermes`/`sigma loop` (below) —
they call the stage library internally. (The old per-stage `sigma spec …`
wrappers were retired; `claude -p` as an amnesiac subprocess was strictly
weaker than running `/spec` in-session.)

`tasks.md` lines look like this (parsed by the loop + board):

```markdown
- [ ] T1 (nlp): tokenize corpus
- [x] T2 (mlops): register model
- [ ] T3 (rl): eval policy
```

---

## 3. `sigma loop` — autonomous maker→checker cycles

Discovers incomplete tasks, runs an **implementer** then a distinct **checker**
per task, ratchets failures into `skills/`.

```bash
# Plan only (safe default) — shows what it WOULD do, runs nothing.
$ sigma loop --topic "$T"
→ sigma loop — 2 pending / 3 total
    max_cycles: 20  (sequential cycles, one workspace)
    • T1 [nlp] tokenize corpus
      cycle=sigma-loop-t1 maker≠checker=True
  (plan only — pass --execute to run maker→checker cycles)

# Execute real cycles.
$ sigma loop --topic "$T" --execute
→ ✓ ran 2 cycle(s): 1 passed, 1 failed
    ✓ tokenize corpus
    ✗ eval policy
      ratcheted → skills/verify-failed-eval-policy/SKILL.md
```

**Rules enforced:**
- Maker ≠ checker — passing the same runner instance raises `ValueError`.
- Verdict parsing is skeptical — a checker reply missing `VERDICT: PASS` = FAIL.
- A failed cycle writes a `SKILL.md` lesson AND that lesson is **recalled** into
  future cycles in the same domain (the closed loop — see §4c).

**Keep the Mac awake** for a long run (macOS only — wraps `caffeinate`):

```bash
$ sigma loop --topic "$T" --execute --keep-awake
→   ☕ keep-awake on (caffeinate)
  ... cycles run without the display/idle sleep timer kicking in ...
```

→ No-ops cleanly off macOS or if `caffeinate` is missing, so it's always safe to
pass. caffeinate is torn down when the run ends (even on error).

### 3a. TDD mode — `--tdd` (test-first cycles)

A distinct **test-writer** agent pens a FAILING test (RED) *before* the
implementer exists; the implementer's prompt is then prefixed with that test and
told to make it pass without weakening it (GREEN). One agent codes, another tests,
a third checks — all enforced distinct.

```bash
$ sigma loop --topic "$T" --execute --tdd
→   🧪 TDD mode: a distinct agent writes a failing test before each implementer
  ✓ tokenize corpus
    test-first: ✓ written
```

→ If test-writing fails, the cycle aborts (nothing to build against) and ratchets
the failure — the implementer never runs. Test artifacts land in `tests/`.

### 3b. Team mode — `--team` (parallel tasks)

Independent tasks run **concurrently**, each its own full cycle. The past-lessons
recall snapshot is pre-built before fan-out, so parallel threads only read it
(race-free, deterministic). Result order matches task order.

```bash
$ sigma loop --topic "$T" --execute --team
→   👥 team mode: independent tasks run in parallel
  ✓ tokenize corpus
  ✓ train agent

# Compose: parallel tasks, each test-first, triple-checked.
$ sigma loop --topic "$T" --execute --team --tdd --logic
```

→ `--logic` adds the logic-evaluator axis (next section). Combine any of
`--team --tdd --logic` freely.

---

## 4. Logic-evaluator — the second verify axis

Every domain ships `context-engines/<domain>/verifiers/logic-evaluator.md`. It
grades **reasoning + plan↔implementation coherence**, NOT code style — a clean
implementation of the *wrong logic* FAILS.

- It runs as an optional **third distinct agent** in a loop cycle.
- A cycle passes only when **both** the code-quality verifier AND the logic
  evaluator return `VERDICT: PASS`.
- Separation enforced: the logic checker must differ from maker and checker
  (`ValueError` otherwise).

Inspect one:

```bash
$ sed -n '1,20p' context-engines/rl/verifiers/logic-evaluator.md
→ # Logic Evaluator: RL
  ... MDP framing, reward design, algorithm fit, eval validity ...
  End with: VERDICT: PASS  or  VERDICT: FAIL
```

In code (how the loop wires it), see `run_loop(..., make_logic_checker=...)` in
`cli/loop.py`. NLP and RL evaluators are deep; the other 7 are lean.

---

## 4a. wakeAgent gate — skip work, spend zero tokens

A cheap pre-check before a loop run or hermes hop. Your gate script prints
`{"wakeAgent": true|false}`; false = nothing to do = skip (no agents, no tokens).

```bash
# a gate that only wakes when the inbox has files
$ cat check-inbox.sh
#!/bin/sh
[ -n "$(ls ~/research/inbox/*.md 2>/dev/null)" ] \
  && echo '{"wakeAgent": true}' || echo '{"wakeAgent": false}'

$ sigma loop --topic "$T" --execute --gate ./check-inbox.sh
→ sigma loop — 1 pending / 1 total
  gate: nothing to do — skipped (0 tokens)

$ sigma hermes "continue" --topic "$T" --gate ./check-inbox.sh
→ stops before the hop if the gate says skip
```

→ **Fail-safe:** a missing / erroring / unparseable gate defaults to WAKE — a
broken gate never silently blocks the pipeline. Gating is opt-in (`--gate`).

## 4b. Contradiction flagging — lessons that disagree

When the loop ratchets a new lesson that conflicts with an existing one (same
domain + same topic), it flags rather than piles up silently.

```bash
$ sigma loop --topic "$T" --execute
→ ✗ tokenize corpus
    ratcheted → skills/verify-failed-tokenize-corpus/SKILL.md
    ⚠ contradiction flagged → skills/CONTRADICTIONS.md
```

→ The new SKILL.md gets a `⚠ CONTRADICTION` marker; `skills/CONTRADICTIONS.md`
logs the conflict. Never auto-resolved, never deleted — you decide.

---

## 4c. The closed learning loop — lessons recalled, not just recorded

Writing a lesson is only half the loop. sigma also **reads lessons back**: before
each loop cycle it loads the past lessons for that task's domain and prepends them
to the implementer + checker prompts — so a mistake made once is fed forward as
"avoid repeating this."

```bash
$ sigma loop --topic "$T" --execute
→   recalled past lessons for domain 'nlp'      # injected into the nlp cycle
    ✓ tokenize corpus                            # maker saw prior nlp lessons
```

- **Selection is by domain** — a lesson tagged `domain: nlp` is recalled for nlp
  tasks. Skills without a `domain:` (vendor, sigma-present, sigma-domains) are
  never recalled.
- **Fed to maker + checker, not the logic evaluator** (it grades reasoning, not
  domain patterns). No lessons → prompts unchanged (fail-safe).
- **In-session:** the `sigma-lessons` skill does the same recall when you work
  via slash commands instead of the CLI loop.

### `/sigma-learn-lesson` — capture a lesson outside the loop

You don't need a loop failure to teach sigma. In Claude Code, after a mistake:

```
/sigma-learn-lesson
→ agent reviews this session, extracts the mistake + lesson + domain,
  writes skills/<slug>/SKILL.md (same format + contradiction check as the loop)
```

That lesson is then recalled on the next run in its domain, exactly like a
loop-born one. Same store, same format, one recall path.

---

## 4d. `sigma weave` — weave artifacts into one HTML chain

Turn the per-stage markdown artifacts into a single self-contained page (human
view) plus a machine manifest.

```bash
$ sigma weave --topic "$T"
→ ✓ wrote .../chain.json        # machine manifest (pure, deterministic)
  ✓ wrote .../chain.html        # one navigable page, all stages cross-linked
    ✓ chain.html valid
```

- **Derived, never authoritative** — markdown stays the source of truth; deleting
  `chain.html`/`chain.json` never affects the pipeline.
- `chain.json` is written FIRST and is agent-independent (exists even if the HTML
  agent run fails).
- The **verify stage** reads `chain.json` to review against the WHOLE chain, not
  just `spec.md` (falls back to `spec.md` if no manifest — fail-safe).
- In-session: the `sigma-present` skill exports a single artifact; `weave` chains
  them all.

---

## 5. Hermes — the optional conductor

Talk plain language; Hermes routes to the right stage and runs it. **Additive** —
standalone `sigma <stage>` still works exactly as before.

### 5a. Single-step (default) — one hop, then stop

```bash
$ sigma hermes "continue" --topic "$T"
→ σ hermes — topic='...' mode=single-step
    • ran propose            # state-driven: research.md exists → next is propose
  ✓ hermes ran 1 stage(s)
```

→ Routing is **state-driven** by default (inspects which artifacts exist — zero
model cost). Emits an event + a line to `hermes-log.md`.

### 5b. Intent override — jump around

```bash
$ sigma hermes "skip ahead to verify" --topic "$T"
→ • ran verify            # "skip"/"verify" signals an override → 1 model call to classify
```

→ Override is triggered by jump words ("redo", "skip", "go back", "again") or an
explicit stage name. Unparseable classification falls back to the state stage.

### 5c. `--auto` — chain until a human gate

```bash
$ sigma hermes "build the whole thing" --topic fresh-idea --auto
→ • ran research
  • ran propose
  • ran blueprint
  • ran spec
  → stopped at gate: spec-approval     # pauses for human review
```

→ Auto chains stages, pausing at **human gates** (spec-approval, verify-failed),
on a stage failure, or at the hop budget (`max_hops`, default 12).

### 5d. `--terse` — compressed output

```bash
$ sigma hermes "continue" --topic "$T" --terse
→ injects the bundled caveman skill so stage output is ~75% smaller.
```

### 5e. `--keep-awake` — don't let the Mac sleep

```bash
$ sigma hermes "build the whole thing" --topic fresh-idea --auto --keep-awake
→   ☕ keep-awake on (caffeinate)
  ... a long auto chain runs without the Mac sleeping ...
```

→ macOS only; wraps `caffeinate`. No-ops elsewhere. Same flag on `sigma loop`.

**Stage → skill injection** (`cli/skill_map.py`): propose/blueprint→brainstorming,
spec→writing-plans, implement-task→TDD, verify→systematic-debugging +
verification-before-completion, `--terse`→caveman.

---

## 6. `sigma board` — kanban

Pure projection over `tasks.md` + `events.jsonl`. Hermes/loop append events; the
board never mutates state.

```bash
# Static snapshot.
$ sigma board --topic "$T"
→ ╭── To Do (0) ──╮╭ In Progress (1)╮╭── Blocked (1) ─╮╭─── Done (1) ───╮
  │ —             ││ T1 tokenize    ││ T3 eval policy ││ T2 register    │
  │               ││ corpus (nlp)   ││ (rl)           ││ model (mlops)  │
  ╰───────────────╯╰────────────────╯╰────────────────╯╰────────────────╯

# Live — redraws as agents progress (Ctrl-C to stop).
$ sigma board --topic "$T" --watch
```

→ Columns: **To Do / In Progress / Blocked / Done**. A task moves by its latest
event (`in_progress`, `failed`→Blocked, `done`); a `- [x]` checkbox alone counts
as Done. Missing workspace → `✗ no spec workspace ...` and exit 1.

Event shape in `events.jsonl` (one JSON object per line):

```json
{"task":"T1","stage":"implement-task","status":"in_progress","ts":"2026-06-17T10:00:00"}
{"task":"T3","stage":"verify","status":"failed","verdict":"FAIL","ts":"2026-06-17T10:05:00"}
```

---

## 7. Bundled skills — `skills/vendor/`

sigma vendors a self-contained skill set so it works even without the upstream
plugins, and so each skill is usable **standalone** in Claude Code.

```bash
$ find skills/vendor -name SKILL.md
→ skills/vendor/superpowers/brainstorming/SKILL.md
  skills/vendor/superpowers/writing-plans/SKILL.md
  skills/vendor/superpowers/test-driven-development/SKILL.md
  skills/vendor/superpowers/systematic-debugging/SKILL.md
  skills/vendor/superpowers/verification-before-completion/SKILL.md
  skills/vendor/caveman/SKILL.md
```

- **Standalone:** invoke any of these directly in Claude Code (e.g. the
  brainstorming skill) independent of sigma.
- **Via Hermes:** auto-injected per stage (section 5).
- These are unmodified upstream copies — don't edit in place; re-vendor (see
  `skills/vendor/README.md` for provenance + refresh steps).

---

## 8. `sigma-present` skill — export to shareable HTML

Turn any sigma artifact into a single portable `.html` you can email or print.

Invoke the skill in Claude Code with an artifact in mind. Three modes:

| You say | Mode | Output |
|---------|------|--------|
| "turn this spec into slides" | DECK (reveal.js) | one `.html`, fragments, speaker notes, `?print-pdf` |
| "export the research as a report" | REPORT (scroll) | long-scroll page, scroll-driven motion |
| "make a deck from the board" | KANBAN | column/card snapshot + Chart.js doughnut |

```bash
# templates the skill emits from:
$ ls skills/sigma-present/templates/
→ deck.reveal.html  report.scroll.html  kanban.board.html
$ ls skills/sigma-present/
→ SKILL.md  THEMES.md  INGEST.md  templates/
```

Built in: 5 named themes (`THEMES.md`), artifact→section mapping (`INGEST.md`),
`prefers-reduced-motion` guard, IntersectionObserver fallback for the report
mode, citations + a "Generated by sigma" provenance footer, and PDF export
(deck: open with `?print-pdf`; report/kanban: browser Print).

---

## 9. `sigma launch` & default

```bash
$ sigma launch              # open Claude Code with sigma context loaded
$ sigma launch --no-launch  # print context, don't spawn claude
$ sigma                     # no subcommand → same as launch (prints context)
```

---

## 9a. `sigma onboard` — friendly first-run setup

Interactive (real TTY). The curl|sh installer points you here.

```bash
$ sigma onboard
→ σ logo + a health snapshot (same checks as `sigma doctor`)
  1. classic-ml   2. deep-learning   …   9. llm-engineering
  Domains (e.g. 1,3 — blank = all): 3,4
  ✓ wrote sigma.config.yml (nlp, rl)
  GEMINI_API_KEY (blank to skip): ******      # hidden; → ~/.sigma/.env (chmod 600)
  OPENAI_API_KEY (blank to skip):             # blank = skipped
  ℹ present CLIs (auth as needed) — claude: …; gpt: `gpt auth login`
  Install RTK (60-90% token saver) and activate it for Claude? [y/N] y
  ✓ RTK set up — restart Claude Code for it to take effect
  ✓ onboarding complete.
```

→ Secrets go to `~/.sigma/.env` (chmod 600, git-ignored), **never** the committed
config. RTK install/activate is confirm-gated (it edits global `settings.json`).
Idempotent — safe to re-run.

## 9b. `sigma doctor` — diagnose + repair

```bash
$ sigma doctor                 # full report; confirm each fix
$ sigma doctor --check         # read-only; exit 1 if anything fails (CI gate)
$ sigma doctor --yes           # apply every fix without prompting
$ sigma doctor --update        # pull sigma + re-vendor skills, then check
→ ✓ python · ✓ deps · ✓ models · ⚠ secrets · ✓ vendored-skills · ✓ plugin
  ✓ config · ✓ workspaces · ✓ rtk
```

→ Checks: Python 3.9+, pyyaml+rich, model CLIs + auth, API keys, vendored skills,
plugin manifest, config validity, workspace/events integrity, and RTK status
(installed + hook active + `rtk gain` works — catches the name-collision binary).

---

## 10. End-to-end example (cold start → board)

```bash
$ sigma init --name demo --domains nlp,rl
$ sigma hermes "research and draft a spec for a sentiment classifier" \
      --topic sentiment-clf --auto
→ runs research → propose → blueprint → spec, stops at spec-approval gate
# in Claude Code: /tasks                      # human-approved: break into tasks
$ sigma board --topic sentiment-clf          # see the task columns
$ sigma loop  --topic sentiment-clf --execute   # maker→checker (+ logic axis)
$ sigma board --topic sentiment-clf --watch  # watch cycles land live
# then, in Claude Code: invoke sigma-present to export spec.md as a deck.
```

---

## 11. Team-change review — `sigma profile` + `sigma review` + `sigma cost`

Distinct from the `verify` STAGE (which grades sigma's OWN pipeline artifacts):
this reviews **team-authored changes** — a local diff or a PR — through three
distinct agents, grounded in the codebase's own logic invariants.

### 11a. `sigma profile` — capture the codebase's invariants

Run **once per repo** (refresh after big logic changes). Walks the code and writes
`sigma/profile/logic-profile.md`: ML-logic invariants (splits, leakage guards,
metrics, reward, eval-determinism) + system-logic invariants (control flow, data
contracts, concurrency, API boundaries).

```bash
$ sigma profile
→ σ profile — codebase at /path/to/repo
  ✓ wrote sigma/profile/logic-profile.md
    ✓ both invariant sections present

$ sigma profile --dry-run     # print the prompt, spend zero tokens
```

### 11b. `sigma review` — three-axis review of a change set

```bash
$ sigma review                 # local uncommitted vs HEAD
$ sigma review main..HEAD      # a git range
$ sigma review 42              # PR #42 (gh pr diff) — also posts a summary comment
$ sigma review --check         # CI gate: exit 1 on CRITICAL/HIGH or inconclusive axis
```

Three **distinct** agents (maker≠checker analog), same context bundle, different
lens: **code** (bugs/security/quality), **ml-logic** (leakage/metrics/reward vs the
profile + the domain `logic-evaluator.md`), **system-logic** (control flow,
contracts, concurrency, API boundaries).

```
→ σ review — main..HEAD
  ✓ wrote sigma/reviews/main-head/review.md
    domains: classic-ml
    verdict: ❌ FAIL — 3 blocking (CRITICAL/HIGH) finding(s)
      ratcheted → skills/review-finding-target-leakage-.../SKILL.md
```

- **Gate** fails on any CRITICAL/HIGH finding OR an inconclusive axis (a dead axis
  is never a silent pass — skeptical).
- **Grounding fail-safe:** no profile → reviews on diff + lessons only (with a
  banner); stale profile → warns, proceeds.
- CRITICAL/HIGH findings **ratchet into `skills/`** and are recalled next review
  (closed loop, like the loop's lessons).

### 11c. `sigma cost` — the heavy-op cost ledger

```bash
$ sigma cost
→ # sigma cost
  Total recorded: ~24,000 tokens across 2 run(s).
  - review: ~24,000 tokens over 2 run(s) (est drift +0)
```

Heavy ops (review/profile/loop/research) estimate cost up front (with per-axis
model-tier routing — cheap model for `code`, strong for `ml-logic`) and record
actual spend into `sigma/costs.jsonl`. Calibrates over time. The `sigma-cost` skill
surfaces the same advice in-session; composes with RTK/caveman, never duplicates.

> Plugin: `/profile` and `/review` are the in-session slash-command equivalents.

---

## 12. `sigma learn` — codebase map grounded in a knowledge graph

```bash
$ sigma learn                  # ARCHITECTURE.md + .tours/<slug>.tour, graph-grounded
$ sigma learn --no-graph       # skip the graphify build (plain agent read)
$ sigma learn --persona "new backend dev" --dry-run
```

`sigma learn` drives an agent to emit an `ARCHITECTURE.md` + a CodeTour `.tour`. When
**graphify** is installed, learn first builds (incrementally) a real dependency graph
of the repo — god-nodes, communities, call/import edges — and injects graphify's
`GRAPH_REPORT.md` into the agent prompt, so the map is grounded in *extracted*
structure, not an eyeball read.

- **Shells out, never imports.** graphify needs py3.10+; sigma stays 3.9 and runs the
  standalone `graphify` binary (installed in its own env by `sigma onboard` / the
  installer — `uv tool install graphifyy`).
- **Always-on + fail-safe.** Absent graphify or a failed build → a plain agent read
  (the prompt is byte-identical to the no-graph case). `--no-graph` skips it outright.
- Code extraction is local tree-sitter → **free, no API key**; `--update` re-extracts
  only changed files, so re-runs are cheap.

## 12a. `sigma scout` — keep the skill bundle fresh from skillsmp.com

```bash
$ sigma scout                  # candidates for your domains, install on approval
$ sigma scout --recent         # sort by newly-added (catch trends)
$ sigma scout --vendor         # maintainer: clone into skills/vendor/ for the bundle
$ sigma scout --dry-run        # show the ranked table, install nothing
```

Queries [skillsmp.com](https://skillsmp.com) per sigma domain, scores relevance
(**domain fit beats popularity** — a viral but off-topic skill never wins), dedups
against what's already bundled, and surfaces a ranked table. **Nothing auto-installs**
— you confirm each skill (and check its license) before it's cloned.

```
→ σ scout — skillsmp.com, domains: classic-ml, …, llm-engineering
  target: project skills (.claude/skills)

  1. rag-eval-kit   ★320  [owner/rag-eval-kit]
     RAG evaluation harness: faithfulness, recall@k, citation grounding
  …
```

- stdlib `urllib` only (no new dependency). Optional `SKILLSMP_API_KEY` in
  `~/.sigma/.env` raises the daily rate limit; anonymous works at a lower rate.
- Fail-safe: API down/rate-limited → empty result + a banner, never a crash.

## 12b. `sigma prune` — cut unused MCP/plugin context bloat

```bash
$ sigma prune                  # surface loaded-but-unused items → confirm each
$ sigma prune --check          # read-only; exit 1 if prunable bloat exists (CI)
$ sigma prune --yes            # disable all prunable plugins without prompting
```

Every enabled plugin + connected MCP server injects its tool schemas into **every**
context. Prune inventories what's loaded, estimates each item's context weight, scans
recent transcripts for actual usage, and ranks the **loaded-but-unused** heaviest-first.

```
→ σ prune — loaded MCP servers + plugins vs recent usage
  21 loaded-but-unused item(s) (~73,000 ctx tokens, scanned 40 transcript(s)):
  1. [mcp-user] atlassian   ~8,000 tok  (manual: user-level MCP)
  3. [plugin]   firebase    ~3,000 tok
  …
```

- **Reversible, never destructive** — disabling flips `enabledPlugins=false` (immutable
  settings merge; every other key preserved). The plugin stays installed; re-enable
  anytime. User-level MCP servers are surfaced for a manual `~/.claude.json` edit.
- **Never prunes on absent evidence** — no transcripts → surfaces nothing (an item with
  unknown usage is treated as *used*).
- Distinct hygiene layer: **scout grows** the bundle, **prune trims** it, **`sigma cost`
  sizes** it. Orthogonal to RTK (proxy tokens) + caveman (output terseness).

> Plugin: `/learn`, `/scout`, `/prune` are the in-session slash-command equivalents.

---

## Cheat sheet

| Command | What |
|---------|------|
| `sigma init --domains a,b` | scaffold config |
| `sigma research "<t>"` | multi-model cited research (real parallel CLI fan-out) |
| `sigma research "<t>" --web` / `--deep` | quick / exhaustive web-grounded research |
| `/propose` … `/verify` (in Claude Code) | run a pipeline stage in-session (loads domain context) |
| `/sigma-learn-lesson` (in Claude Code) | capture a lesson from this session → ratcheted skill |
| `sigma loop --topic <t>` | plan cycles (safe) |
| `sigma loop --topic <t> --execute` | run maker→checker (+logic) cycles |
| `... --tdd` / `--team` / `--logic` | test-first / parallel tasks / add logic axis (combine) |
| `sigma profile` | walk codebase → logic-profile.md (grounds review) |
| `sigma review [PR\|a..b]` | three-axis review (code/ml-logic/system-logic) |
| `sigma review --check` | CI gate: exit 1 on CRITICAL/HIGH or inconclusive axis |
| `sigma cost` | token-cost ledger for heavy ops |
| `sigma learn` | codebase map → ARCHITECTURE.md + .tour (graphify-grounded if installed) |
| `sigma learn --no-graph` | skip the knowledge-graph build |
| `sigma scout` | discover relevant skills on skillsmp.com → install on approval |
| `sigma scout --vendor` / `--recent` | clone into the sigma bundle / sort by newest |
| `sigma prune` | surface loaded-but-unused MCP/plugins → reversible disable |
| `sigma prune --check` | CI gate: exit 1 if prunable context bloat exists |
| `... --keep-awake` | (loop/hermes) prevent Mac sleep during the run |
| `... --gate <script>` | (loop/hermes) skip work if wakeAgent says nothing to do |
| `sigma hermes "<msg>" --topic <t>` | conductor: route + run one stage |
| `sigma hermes "<msg>" --topic <t> --auto` | chain to a human gate |
| `sigma hermes "<msg>" --topic <t> --terse` | compressed output |
| `sigma board --topic <t>` | kanban snapshot |
| `sigma board --topic <t> --watch` | live kanban |
| `sigma weave --topic <t>` | weave artifacts → chain.html + chain.json |
| `sigma onboard` | first-run setup: domains, API keys, RTK, caveman, statusline, graphify |
| `sigma doctor` | diagnose + confirm-gated fixes |
| `sigma doctor --check` | read-only health (CI gate, exit 1 on fail) |
| `sigma doctor --yes` / `--update` | auto-fix / pull+re-vendor then check |
| `sigma launch` | open Claude Code with context |

See [`CLAUDE.md`](../CLAUDE.md) for layout + gotchas and the
[`README`](../README.md) for the design rationale.
