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
→ usage: sigma [-h] [--version] {init,research,doctor,onboard,learn,session-context,
  uninstall,setup-repo,scout,prune,profile,review,claude-md-check,docs-check,
  claude-md-create,cost,usage}

# from a clone, without installing:
$ python3 -m cli.main --help

# dev checks (must stay green)
$ python3 -m pytest tests/ -q          # all pass
$ python3 -m ruff check cli/ tests/ hooks/ scripts/    # All checks passed!
```

### Or install as a Claude Code plugin (slash commands + skills)

```
/plugin marketplace add navidgh66/sigma     # or a local clone path
/plugin install sigma@sigma
```

→ **sigma is plugin-first.** Every stage is a native slash command — `/research
/propose /blueprint /grill /spec /tasks /implement-task /verify /loop /craft /e2e
/sigma-learn-lesson` — the role agents live in `agents/`, the loop guard in
`hooks/`, and `sigma-present`, `sigma-domains`, `sigma-lessons` are native skills.
The pipeline **stages and the loop run in-session** (they load the domain
context-engine and are steerable).
The `sigma` CLI keeps only what Claude Code can't do in-session (parallel
`research`), review/profile, and setup + hygiene.

---

## 1. `sigma init` — scaffold a project

Pick the domains a project needs; writes `sigma.config.yml`.

```bash
$ sigma init --name churn-model --domains classic-ml,data-analysis
→ ✓ wrote /path/sigma.config.yml
    domains: classic-ml, data-analysis
    models:  claude, gpt

$ sigma init --domains nlp,rl           # name defaults to cwd
$ sigma init --force                    # overwrite existing config
$ sigma init --domains bogus            # ✗ unknown domain(s): bogus  (lists valid)
```

The 9 valid domains: `classic-ml deep-learning nlp rl data-analysis
data-engineering ai-agent-engineering mlops llm-engineering`.

Local override: drop a `sigma.config.local.yml` next to it — deep-merged on load
(git-ignore it for machine-specific tweaks).

---

## 2. The pipeline

```
research → propose → blueprint →[grill]→ spec →[grill]→ tasks → implement-task → verify → loop
```

Each stage reads the **prior** stage's artifact as context and writes its own.
Run a stage **in-session** as a slash command (`/spec`, `/tasks`, …) — it loads
the matching domain context-engine via the `sigma-domains` skill. (`sigma
research` stays a CLI command for real parallel fan-out.)

### 2a. `sigma research` — multi-model, cited

Fans out to Claude + GPT (via codex) in parallel (whichever CLIs are installed),
aggregates + dedupes + cites into `research.md`.

```bash
$ sigma research "active learning for imbalanced fraud labels"
→ sigma research — topic='active learning for imbalanced fraud labels'
    models requested: claude, gpt
    models available: claude            # gpt skipped if the codex CLI is absent
  ✓ wrote sigma/specs/2026-06-17-active-learning-for-imbalanced-fraud-labels/research.md
  → next: /propose

$ sigma research "topic" --models claude          # restrict models
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
/verify           # spec.md (+ the other workspace artifacts) → verify/
```

Run them in the session for the topic's workspace. `/craft` chains the back half
(`spec → grill → tasks → loop`) from a design you bring.

`tasks.md` lines look like this (read by `/loop`):

```markdown
- [ ] T1 (nlp): tokenize corpus
- [x] T2 (mlops): register model
- [ ] T3 (rl) [scenario: policy beats baseline]: eval policy
```

---

## 3. `/loop` — the in-session loop

`/loop` runs every open task in `tasks.md` to done in your Claude Code session.

```
/loop
→ wrote sigma/specs/2026-09-24-sentiment-clf/loop-state.json (3 tasks)
  T1 (nlp) tokenize corpus: implementing…
  T1 passed (verifier: 14 tests passed, quoted)
  T2 (mlops) register model: tamper guard flagged tests/test_registry.py, retrying
  T2 passed on attempt 2
  T3 (rl) eval policy: e2e FAIL after 3 attempts → failed, lesson ratcheted
  recap: 2 passed, 1 failed (skills/loop-failed-eval-policy/SKILL.md)
```

Per task, with distinct agents from the plugin's `agents/`:

1. **Snapshot tests** — `scripts/test_guard.py snapshot` hashes every test file.
2. **`sigma-implementer`** (effort medium) builds the task against its BDD scenario
   and up to 5 recalled lessons for its domain.
3. **Tamper guard** — `scripts/test_guard.py check`: an edited or deleted
   pre-existing test fails the attempt and `restore` puts the originals back from
   the snapshot's copies. New tests are fine.
4. **`sigma-verifier`** (effort medium, no Edit/Write tools) runs the tests itself,
   quotes the evidence, and ends with `VERDICT: PASS` or `FAIL` (no verdict = FAIL).
5. **`sigma-e2e`** (only for `[scenario: ...]` tasks) drives the scenario live:
   PASS / FAIL / ERROR, where ERROR (app unreachable) never fails the attempt.
6. Pass → the task is ticked in `tasks.md`. Fail → up to 2 retries with the
   verifier's findings, then `failed` + a ratcheted lesson.

### 3a. Why it doesn't stop halfway — the Stop hook

`loop-state.json` is the checklist. The plugin's `hooks/loop_guard.py` runs on
every Stop: while a running loop has open tasks and no `blocker`, it sends the
session back ("Your loop still has open tasks: T3 (…). Continue with them. If one
is blocked, set `blocker` …"). It allows the stop after 3 nudges without progress
(status `stopped`), when a blocker is recorded, or when every task is settled, and
it fails open on any error. This is the Opus 5.5 guide's advice for unattended
runs: a text-only end of turn is a report, not proof the work is done.

### 3b. Modes

- **Test-first** — say "TDD": `sigma-test-writer` (effort low) writes the failing
  test first, then the snapshot is retaken so that test is protected too.
- **Parallel** — say "in parallel" (needs a clean working tree, else it runs
  serially): the lead creates a git worktree per independent task
  (`.worktrees/<run>-<id>`), snapshots its tests there, dispatches the implementers
  together, checks each in its own worktree and merges it back on pass (a conflict
  is aborted and the task marked `blocked`); it tracks `elapsed Ns / Bs` against a
  time budget.
- **Time budget** — give one ("you have 30 minutes") and it lands in
  `budget_seconds`; the Stop hook's nudge carries `elapsed / budget`.

### 3c. Lessons — capped, newest first, contradiction-safe

A failed task writes `skills/<slug>/SKILL.md` with `metadata: domain:` and
`created:`. Recall (in `/loop`, `sigma review` and the `sigma-lessons` skill)
takes the **5 newest** for the domain. A second lesson on the same topic never
overwrites the first: it lands in `<slug>-2/` with a `⚠ CONTRADICTION` marker and
a line in `skills/CONTRADICTIONS.md`, for you to resolve.

### `/sigma-learn-lesson` — capture a lesson outside the loop

```
/sigma-learn-lesson
→ agent reviews this session, extracts the mistake + lesson + domain,
  writes skills/<slug>/SKILL.md (same format + contradiction check as the loop)
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
  skills/vendor/code-tour/SKILL.md
```

- **Standalone:** invoke any of these directly in Claude Code (e.g. the
  brainstorming skill) independent of sigma.
- **Via `sigma learn`:** `codebase-onboarding` + `code-tour` are injected into the
  learn agent's prompt.
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

```bash
# templates the skill emits from:
$ ls skills/sigma-present/templates/
→ deck.reveal.html  report.scroll.html
$ ls skills/sigma-present/
→ SKILL.md  THEMES.md  INGEST.md  templates/
```

Built in: 5 named themes (`THEMES.md`), artifact→section mapping (`INGEST.md`),
`prefers-reduced-motion` guard, IntersectionObserver fallback for the report
mode, citations + a "Generated by sigma" provenance footer, and PDF export
(deck: open with `?print-pdf`; report: browser Print).

---

## 9a. `sigma onboard` — friendly first-run setup

Interactive (real TTY). The curl|sh installer points you here.

```bash
$ sigma onboard
→ σ logo + a health snapshot (same checks as `sigma doctor`)
  1. classic-ml   2. deep-learning   …   9. llm-engineering
  Domains (e.g. 1,3 — blank = all): 3,4
  ✓ wrote sigma.config.yml (nlp, rl)
  OPENAI_API_KEY (blank to skip):             # blank = skipped
  FIRECRAWL_API_KEY (blank to skip): ******   # hidden; → ~/.sigma/.env (chmod 600)
  ℹ present CLIs (auth as needed) — claude: …; gpt: `codex login --device-auth`
  Sign in to Codex now with a device code (open the printed URL, enter the code; …)? [y/N] y
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

## 10. End-to-end example (cold start → working code)

```bash
$ sigma init --name demo --domains nlp,rl
$ sigma research "sentiment classifier for support tickets" --web
# in Claude Code:
/propose → /blueprint → /grill → /spec → /grill → /tasks
/loop                     # every task to done; the Stop hook keeps it going
/review                   # 3-axis review before merging
# then invoke sigma-present to export spec.md as a deck.
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
surfaces the same advice in-session; composes with RTK, never duplicates.

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
  sizes** it. Orthogonal to RTK (proxy tokens).

> Plugin: `/learn`, `/scout`, `/prune` are the in-session slash-command equivalents.

---

## Cheat sheet

| Command | What |
|---------|------|
| `sigma init --domains a,b` | scaffold config |
| `sigma research "<t>"` | multi-model cited research (real parallel CLI fan-out) |
| `sigma research "<t>" --web` / `--deep` | quick / exhaustive web-grounded research |
| `/propose` … `/verify` (in Claude Code) | run a pipeline stage in-session (loads domain context) |
| `/grill`, `/grill-loop` | adversarial gate on blueprint/spec; bounded auto-fix loop |
| `/craft` | bring a design → spec → grill → tasks → loop |
| `/loop` | run every open task to done (role agents, Stop-hook guard, tamper guard) |
| `/e2e` | run spec.md's BDD scenarios live |
| `/sigma-learn-lesson` | capture a lesson from this session → ratcheted skill |
| `sigma profile` | walk codebase → logic-profile.md (grounds review) |
| `sigma review [PR\|a..b]` | three-axis review (code/ml-logic/system-logic) |
| `sigma review --check` | CI gate: exit 1 on CRITICAL/HIGH or inconclusive axis |
| `sigma cost` | token-cost ledger for heavy ops |
| `sigma usage` | real Claude Code token/cache/cost via ccusage |
| `sigma learn` | codebase map → ARCHITECTURE.md + .tour (graphify-grounded if installed) |
| `sigma learn --no-graph` | skip the knowledge-graph build |
| `sigma scout` | discover relevant skills on skillsmp.com → install on approval |
| `sigma scout --vendor` / `--recent` | clone into the sigma bundle / sort by newest |
| `sigma prune` | surface loaded-but-unused MCP/plugins → reversible disable |
| `sigma prune --check` | CI gate: exit 1 if prunable context bloat exists |
| `sigma docs-check --check` | version parity + stale test-count claims |
| `sigma claude-md-check` / `claude-md-create` | grade / scaffold CLAUDE.md |
| `sigma onboard` | first-run setup: domains, API keys, codex sign-in, RTK, statusline, graphify |
| `sigma setup-repo` | per-repo bootstrap: config + hook + CLAUDE.local + map |
| `sigma doctor` | diagnose + confirm-gated fixes |
| `sigma doctor --check` | read-only health (CI gate, exit 1 on fail) |
| `sigma doctor --yes` / `--update` | auto-fix / pull+re-vendor then check |
| `sigma` | no subcommand → print help |

See [`CLAUDE.md`](../CLAUDE.md) for layout + gotchas and the
[`README`](../README.md) for the design rationale.
