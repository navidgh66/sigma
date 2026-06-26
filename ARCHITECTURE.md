# Sigma Architecture

## What it is

Sigma is a personal, portable AI workflow toolkit for data science and AI engineering.
It is **plugin-first**: a Claude Code plugin (slash commands + skills) you carry into any
repo, backed by a thin CLI for what Claude Code cannot do in-session.

Design philosophy: the developer's output is not code — it is the **system that produces code**
(specs → agents → tests → ratchet). Sigma is that system.

---

## Two surfaces

| Surface | When to use |
|---------|-------------|
| **Claude Code plugin** (primary) | Pipeline stages (`/research` … `/verify`), `/grill`, `skills/sigma-*` — runs in-session with full domain context and human steering |
| **CLI** (`sigma …`) | `research` (parallel multi-model), `loop`/`hermes` (autonomous escape hatch), `board`/`weave` (live TUI / artifact chain), `doctor`/`onboard` (setup) |

---

## Pipeline

```
research → propose → blueprint → [grill-blueprint] → spec → [grill-spec] → tasks → implement-task → verify → loop
```

Artifacts live under `sigma/specs/{YYYY-MM-DD}-{slug}/`. Each stage reads the prior
stage's artifact as context. The `verify` stage reads the **whole chain** via `chain.json`
(built by `sigma weave`). The two `grill-*` stages are adversarial gates that BLOCK the
auto chain on a CRITICAL/HIGH logic flaw.

Stage list defined in `cli/pipeline.py:STAGES`.

---

## Module layout

### Entry point
- `cli/main.py` — argparse CLI; one `cmd_*` function per subcommand; imports from pure modules only

### Core abstractions
- `cli/runner.py` — `AgentRunner` + `AgentResult`; single execution chokepoint; `claude -p <prompt>` subprocess; injectable `runner` for tests
- `cli/pipeline.py` — `STAGES`, `execute_stage`, `chain_context` (full-chain verify context), `render_invocation`
- `cli/loop.py` — `Task`, `CyclePlan`, `CycleOutcome`; `execute_cycle` (maker→checker, optional logic + TDD axes); `run_loop` (sequential or `--team` parallel via `ThreadPoolExecutor`)
- `cli/hermes.py` — conductor: `route` → inject skill → `execute_stage` → append event → gate check; single-step or `--auto` chain
- `cli/intent.py` — hybrid routing: `scan_state` (free, artifact-presence) → `classify` (one model call, only on override signals)

### State / memory
- `cli/events.py` — append-only `events.jsonl`; board state spine
- `cli/board.py` — pure `build_columns` projection + rich static/live render
- `cli/skills_recall.py` — `recall_lessons(skills_dir, domain)` + `render_recall_block`; read side of learning loop
- `cli/skills_index.py` — `topic_key` + `find_contradictions`; contradiction detection on ratchet
- `cli/cost.py` — `estimate / record / calibrate / report`; append-only `sigma/costs.jsonl`
- `cli/trajectory.py` — append-only `trajectory.jsonl` (one step per agent run) + `summarize` projection + `make_sink`; observability, pure like `events.py`

### Evaluation
- `cli/eval.py` — pure: parse eval set (markdown cases), LM-judge prompt, skeptical `parse_grade`, `aggregate`/`gate(threshold)`, `ensure_distinct` (SUT≠judge)
- `cli/eval_run.py` — thin: prompt mode (run SUT → grade w/ distinct judge) or artifact mode, parallel grading, cost record, `--check` gate

### Research
- `cli/research.py` — parallel `ThreadPoolExecutor` fan-out to claude/gemini/gpt; `--web` / `--deep` modes
- `cli/models.py` — per-model adapters (`claude -p`, `gemini -p --output-format json`, `codex exec`); `clean_output`

### Knowledge
- `cli/learn.py` — agent-driven codebase walk → `ARCHITECTURE.md` + `.tours/<slug>.tour`
- `cli/graphify.py` — detect/install/run graphify (py3.10+ isolated env); inject `GRAPH_REPORT.md`
- `cli/codetour.py` — pure CodeTour anchor validator

### Context hygiene
- `cli/scout.py` / `cli/scout_run.py` — skillsmp.com relevance-ranked discovery; never auto-installs
- `cli/prune.py` / `cli/prune_run.py` — unused MCP/plugin surface; reversible disable via immutable settings merge
- `cli/skill_map.py` — stage → bundled skill; `inject_skill` into prompt prefix
- `cli/domains_index.py` — domain → implementer/verifier/logic-evaluator file paths

### Artifacts
- `cli/weave.py` — agent-driven `chain.html`; pure `weave_manifest.build_manifest` writes `chain.json` first (agent-independent)
- `cli/weave_manifest.py` — pure `build_manifest` + `validate_chain_html`
- `cli/review.py` / `cli/review_run.py` — 3-axis diff/PR review (code / ml-logic / system-logic); `ensure_distinct_axes`
- `cli/profile_manifest.py` / `cli/profile_run.py` — `logic-profile.md` (ML-logic + system-logic invariants)

### Setup / health
- `cli/config.py` — `SigmaConfig` + `sigma.config.yml` load/write/validate
- `cli/paths.py` — `DOMAINS` (9), `sigma_home`, `project_root`, `spec_workspace`, `slugify`
- `cli/checks.py` — pure diagnostic probes (return `Check`, never print/mutate)
- `cli/doctor.py` — `run_doctor`; confirm-gated fixes; `--check` CI gate; `--update` dual-surface
- `cli/onboard.py` — first-run wizard
- `cli/secrets.py` — `~/.sigma/.env` (chmod 600); never committed
- `cli/rtk.py` — RTK token saver; confirm-gated; idempotent
- `cli/caveman.py` — caveman terse-output mode; mirrors RTK shape
- `cli/statusline.py` — ccstatusline; immutable settings merge; confirm-gated
- `cli/render.py` — σ logo + rich/plain output helpers
- `cli/keepawake.py` — macOS `caffeinate` wrapper; context manager; best-effort
- `cli/gate.py` — `run_gate`: wakeAgent pre-check; defaults WAKE on error (fail-safe)

### Plugin / commands / skills
- `.claude-plugin/plugin.json` — makes sigma a Claude Code plugin
- `commands/*.md` — slash-command templates (YAML frontmatter + markdown body); one per stage + `/grill` + `/grill-loop` + special commands
- `context-engines/<domain>/` — 9 domains; each has `implementers/`, `verifiers/`, `logic-evaluator.md`
- `skills/sigma-*` — bundled skills loaded on demand (sigma-domains, sigma-grilling, sigma-grill-loop, sigma-scout, sigma-prune, sigma-cost, sigma-lessons, sigma-present)
- `skills/vendor/` — upstream unmodified copies; do not edit in place

### Tests
- `tests/` — 482 pytest tests; pure logic tested with fakes (no real subprocesses)

---

## Key invariants

1. **Maker ≠ checker** — `execute_cycle` enforces `implementer is not verifier` via `ValueError`; same for logic checker and test writer
2. **Skeptical verdicts** — missing `VERDICT: PASS` line → FAIL (loop, hermes, review gate)
3. **Fail-safe everywhere** — missing files → degrade gracefully, never block
4. **Append-only state** — `events.jsonl`, `costs.jsonl`, `loop-log.md`; callers pass `ts`, never generated in pure code
5. **Pure/thin split** — business logic in `cli/*.py` (fully testable); side effects in `*_run.py`
6. **Prompts via argv** — `claude -p <prompt>` never via shell; no injection risk

---

## Data flow: autonomous loop cycle

```
run_loop
  └─ pre-build recall per domain (skills_recall.recall_lessons)
  └─ [--gate] run_gate → skip if wake=false
  └─ execute_cycle(plan, workspace, skills_dir, implementer, verifier, ...)
       ├─ [TDD] test_writer.run(TEST_PROMPT) → write tests/
       ├─ implementer.run(IMPLEMENT_PROMPT + recall + test)
       ├─ write impl/
       ├─ verifier.run(VERIFY_PROMPT + recall)
       ├─ write verify/
       ├─ [logic] logic_checker.run(LOGIC_PROMPT)
       ├─ write verify/*.logic.md
       └─ on FAIL: ratchet_to_skills → SKILL.md + CONTRADICTIONS.md check
                   [TDD] test_writer.run(REGRESSION_PROMPT) → write regressions/
```

---

## Where to start

- **Adding a new pipeline stage**: add to `STAGES` in `cli/pipeline.py`, create `commands/<name>.md`
- **Adding a new CLI subcommand**: add `cmd_<name>` in `cli/main.py`, add parser in `build_parser`
- **Adding a new domain**: add to `DOMAINS` in `cli/paths.py`, create `context-engines/<domain>/`
- **Understanding loop logic**: `cli/loop.py` — all pure, no subprocess, fully testable
- **Understanding routing**: `cli/intent.py` — state-driven by default, model call only on override
- **Understanding cost tracking**: `cli/cost.py` — estimate before, record after, calibrate from ledger
