# Sigma Architecture

## What it is

Sigma is a personal, portable AI workflow toolkit for data science and AI engineering.
It is **plugin-first**: a Claude Code plugin (slash commands, role agents, a Stop hook,
skills) you carry into any repo, backed by a thin CLI for what Claude Code cannot do
in-session plus setup and hygiene.

Design philosophy: the developer's output is not code — it is the **system that produces
code** (specs → agents → tests → ratchet). Sigma is that system. Every harness piece
encodes an assumption about what the model cannot do alone; when a newer model makes one
unnecessary, it goes (0.28.0 retired the CLI loop engine for an in-session `/loop`).

---

## Two surfaces

| Surface | When to use |
|---------|-------------|
| **Claude Code plugin** (primary) | Pipeline stages (`/research` … `/verify`), `/grill`, `/craft`, `/loop`, `/e2e`, `agents/`, `hooks/`, `skills/sigma-*` — in-session with domain context and human steering |
| **CLI** (`sigma …`) | `research` (parallel multi-model), `review`/`profile`, `learn`, and setup + hygiene (`onboard`, `doctor`, `setup-repo`, `scout`, `prune`, `docs-check`, `claude-md-*`, `cost`, `usage`) |

---

## Pipeline

```
research → propose → blueprint → [grill] → spec → [grill] → tasks → implement-task → verify → loop
```

Artifacts live under `sigma/specs/{YYYY-MM-DD}-{slug}/`. Each stage reads the prior
stage's artifact. `/grill` is an adversarial gate that BLOCKs on a CRITICAL/HIGH flaw.
`/craft` drives the back half (`spec → grill → tasks → loop`) from a design you bring.

---

## The in-session loop (`/loop`)

```
/loop (lead, commands/loop.md)
  └─ write loop-state.json (one entry per open task in tasks.md)
  └─ per task:
       ├─ scripts/test_guard.py snapshot         (hash every test file)
       ├─ [TDD] agents/sigma-test-writer          (effort low; failing test first)
       ├─ agents/sigma-implementer                (effort medium; scenario + ≤5 lessons)
       ├─ scripts/test_guard.py check            (edited/deleted old test → attempt fails)
       ├─ agents/sigma-verifier                   (effort medium; no Edit/Write; runs tests, VERDICT)
       ├─ [scenario] agents/sigma-e2e             (effort low; PASS / FAIL / ERROR)
       └─ pass → tick tasks.md · fail → ≤2 retries → failed + ratchet a lesson
  └─ finish: status done, recap

hooks/hooks.json → Stop → hooks/loop_guard.py
  running loop + open tasks + no blocker → block with a nudge naming them
  ≤3 nudges without progress, then status "stopped"; fails open on any error
```

Design sources: the Opus 5.5 prompting guide (text-only end of turn is a report; checklist
+ capped continuations; named early stops; effort as the control; time-budget signals)
and 2025-26 agent research (tests protected from the implementer; checkers that run code;
small capped lesson recall).

---

## Module layout

### Entry point
- `cli/main.py` — argparse CLI; one `cmd_*` function per subcommand; bare `sigma` prints help

### Core
- `cli/runner.py` — `AgentRunner` (`executable`, `timeout`, `runner`, `model`) + `AgentResult`; the single `claude -p <prompt>` chokepoint for CLI agent runs
- `cli/ratchet.py` — `render_skill` / `ratchet_to_skills` / `flag_contradiction`; never overwrites an earlier lesson (`-2`, `-3` suffix)
- `cli/skills_recall.py` — `recall_lessons` (≤5 per domain, newest first by `created`) + `render_recall_block`
- `cli/skills_index.py` — `topic_key`, `parse_skill_meta` (domain/topic/created), `find_contradictions`

### Plugin runtime (stdlib only, no `cli.*` imports)
- `hooks/loop_guard.py` + `hooks/hooks.json` — the `/loop` Stop hook
- `scripts/test_guard.py` — test-file snapshot / check (tamper guard)
- `agents/*.md` — `sigma-implementer`, `sigma-verifier`, `sigma-test-writer`, `sigma-e2e`

### Research
- `cli/research.py` — parallel fan-out to model CLIs + search tools + real synthesis → cited `research.md`
- `cli/research_brief.py` / `cli/research_docs.py` — brief templates + generated doc blocks
- `cli/models.py` — model-CLI adapters (`claude -p`, `gemini -p --output-format json`, `codex exec`); `clean_output`
- `cli/search_providers.py` — Firecrawl search tier (deep mode scrapes top-3 pages)

### Knowledge
- `cli/learn.py` — agent-driven codebase walk → `ARCHITECTURE.md` + `.tours/<slug>.tour`; injects vendored skills
- `cli/graphify.py` — detect/install/run graphify (py3.10+ isolated env); inject `GRAPH_REPORT.md`
- `cli/codetour.py` — CodeTour anchor validator
- `cli/session_context.py` / `cli/session_hook.py` / `cli/claude_local.py` / `cli/claude_md_ref.py` — feed learn artifacts into every session

### Review
- `cli/review.py` / `cli/review_run.py` — 3-axis diff/PR review (code / ml-logic / system-logic); `ensure_distinct_axes`; CRIT/HIGH findings ratchet
- `cli/profile_manifest.py` / `cli/profile_run.py` — `logic-profile.md` (ML-logic + system-logic invariants)
- `cli/graph_impact.py` — graph-impact section from graphify's `graph.json`
- `cli/domains_index.py` — domain → implementer/verifier/logic-evaluator files

### Hygiene
- `cli/scout.py` / `cli/scout_run.py` — skillsmp.com relevance-ranked discovery; never auto-installs
- `cli/prune.py` / `cli/prune_run.py` — unused MCP/plugin surface; reversible disable
- `cli/docs_check.py` / `cli/docs_check_run.py` — version parity + stale test-count claims
- `cli/claude_md_check*.py` / `cli/claude_md_scaffold*.py` — grade / scaffold CLAUDE.md
- `cli/cost.py` — estimate / record / calibrate / report; `sigma/costs.jsonl`
- `cli/usage.py` — ccusage wrapper for real Claude Code spend

### Setup / health
- `cli/config.py`, `cli/paths.py`, `cli/checks.py`, `cli/doctor.py`, `cli/onboard.py`, `cli/setup_repo.py`, `cli/uninstall.py`
- `cli/secrets.py` (`~/.sigma/.env`, chmod 600), `cli/rtk.py`, `cli/statusline.py`, `cli/codex_login.py`, `cli/render.py`

### Plugin content
- `.claude-plugin/plugin.json` + `marketplace.json`
- `commands/*.md` — slash commands (one per stage + `/grill`, `/grill-loop`, `/craft`, `/loop`, `/e2e`, `/learn`, `/scout`, `/prune`, `/profile`, `/review`, `/claude-md-*`, `/sigma-learn-lesson`)
- `context-engines/<domain>/` — 9 domains; `implementers/` + `verifiers/` (with `logic-evaluator.md`)
- `skills/sigma-*` — bundled skills; `skills/vendor/` — upstream copies (do not edit in place)

---

## Key invariants

1. **Maker ≠ checker** — distinct agents; the verifier and e2e agents have no edit tools; `review` axes must be distinct objects (`ValueError`)
2. **Tests are the contract** — the tamper guard fails an attempt that edits or deletes a pre-existing test
3. **Skeptical verdicts** — missing `VERDICT: PASS` → FAIL; missing grill `VERDICT: READY` → BLOCK; missing e2e verdict → ERROR (never a scored FAIL)
4. **Fail-safe hooks** — the Stop hook and SessionStart hook never trap or break a session
5. **Pure/thin split** — business logic in pure modules; side effects in `*_run.py`
6. **Prompts via argv** — `claude -p <prompt>`, never via a shell

---

## Where to start

- **Changing the loop**: `commands/loop.md` (the lead's workflow), `agents/*.md` (roles), `hooks/loop_guard.py` (stop rules)
- **Adding a CLI subcommand**: `cmd_<name>` in `cli/main.py` + a parser in `build_parser`
- **Adding a domain**: `DOMAINS` in `cli/paths.py` + `context-engines/<domain>/`
- **Understanding lessons**: `cli/ratchet.py` (write) and `cli/skills_recall.py` (read)
