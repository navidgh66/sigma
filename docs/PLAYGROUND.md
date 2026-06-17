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
$ python3 -m pytest tests/ -q          # 127 passed
$ python3 -m ruff check cli/ tests/    # All checks passed!
```

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
Run a single stage with `sigma <stage> --topic <t>`.

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
```

→ Missing model CLIs degrade gracefully (skipped, not an error). Every claim in
`research.md` is cited; fact and inference are separated.

### 2b. Generic stages: propose → verify

```bash
T="active learning for imbalanced fraud labels"
$ sigma propose       --topic "$T"     # research.md  → proposals.md
$ sigma blueprint     --topic "$T"     # proposals.md → architecture.md
$ sigma spec          --topic "$T"     # architecture.md → spec.md
$ sigma tasks         --topic "$T"     # spec.md → tasks.md  (domain-routed checklist)
$ sigma implement-task --topic "$T"    # tasks.md → impl/
$ sigma verify        --topic "$T"     # spec.md → verify/
→ ✓ spec → .../spec.md
  → next: /tasks
```

**Dry run** — see the exact prompt sigma would hand Claude, without spawning it:

```bash
$ sigma spec --topic "$T" --dry-run
→ Execute the sigma 'spec' stage.
  Workspace: .../2026-06-17-.../
  Write artifact: .../spec.md
  --- input: architecture.md ---
  <prior artifact chained in as context>
  --- command template ---
  <commands/spec.md>
```

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
    max_cycles: 20  worktrees: True
    • T1 [nlp] tokenize corpus
      worktree=sigma-loop-t1 maker≠checker=True
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
- A failed cycle writes a `SKILL.md` lesson so it never recurs (the ratchet).

**Keep the Mac awake** for a long run (macOS only — wraps `caffeinate`):

```bash
$ sigma loop --topic "$T" --execute --keep-awake
→   ☕ keep-awake on (caffeinate)
  ... cycles run without the display/idle sleep timer kicking in ...
```

→ No-ops cleanly off macOS or if `caffeinate` is missing, so it's always safe to
pass. caffeinate is torn down when the run ends (even on error).

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

## 10. End-to-end example (cold start → board)

```bash
$ sigma init --name demo --domains nlp,rl
$ sigma hermes "research and draft a spec for a sentiment classifier" \
      --topic sentiment-clf --auto
→ runs research → propose → blueprint → spec, stops at spec-approval gate
$ sigma tasks --topic sentiment-clf          # human-approved: break into tasks
$ sigma board --topic sentiment-clf          # see the task columns
$ sigma loop  --topic sentiment-clf --execute   # maker→checker (+ logic axis)
$ sigma board --topic sentiment-clf --watch  # watch cycles land live
# then, in Claude Code: invoke sigma-present to export spec.md as a deck.
```

---

## Cheat sheet

| Command | What |
|---------|------|
| `sigma init --domains a,b` | scaffold config |
| `sigma research "<t>"` | multi-model cited research |
| `sigma <stage> --topic <t>` | run one pipeline stage |
| `sigma <stage> --topic <t> --dry-run` | print prompt, don't run |
| `sigma loop --topic <t>` | plan cycles (safe) |
| `sigma loop --topic <t> --execute` | run maker→checker (+logic) cycles |
| `... --keep-awake` | (loop/hermes) prevent Mac sleep during the run |
| `sigma hermes "<msg>" --topic <t>` | conductor: route + run one stage |
| `sigma hermes "<msg>" --topic <t> --auto` | chain to a human gate |
| `sigma hermes "<msg>" --topic <t> --terse` | compressed output |
| `sigma board --topic <t>` | kanban snapshot |
| `sigma board --topic <t> --watch` | live kanban |
| `sigma launch` | open Claude Code with context |

See [`CLAUDE.md`](../CLAUDE.md) for layout + gotchas, and the
[design doc](2026-06-16-sigma-design.md) for rationale.
