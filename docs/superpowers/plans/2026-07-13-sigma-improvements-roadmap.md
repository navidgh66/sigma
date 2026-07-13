# sigma Improvements Roadmap (6 features)

> Master roadmap for the six improvements agreed on 2026-07-13. Each feature is an
> independent subsystem and gets its OWN detailed implementation plan (per the
> writing-plans scope rule) written just before execution. Feature ⑥ is planned in
> full already: [2026-07-13-orchestration-routing.md](2026-07-13-orchestration-routing.md).

**Baseline:** v0.23.0, 872 test functions green, ruff clean.

## Execution order + rationale

| # | Feature | Size | Depends on | Why this position |
|---|---------|------|-----------|-------------------|
| ⑥ | Orchestration routing | S | — | Smallest; sharpens every hermes/research run used to validate the rest |
| ① | Real token telemetry | M | — | Unlocks measurement the others read; do early so data accumulates |
| ② | Docs-check gate | M | — | Kills the 232/779/872 drift class; protects every later release |
| ④ | Verifier context enrichment | S | — | Cheap loop-quality win; benefits from ① (measure pass-rate delta) |
| ③ | Lesson-efficacy loop | M | ① helpful | Needs trajectory lesson-id recording; richer once telemetry lands |
| ⑤ | Spec→eval autogeneration | M | — | Last: consumes stable scenarios.py + eval.py surfaces |

## Scope cards

### ⑥ Orchestration routing (planned in full — see linked plan)
`routing_for("hermes")` per-stage tier map (planning/grill → strong, execution → mid);
stage-aware runner in `run_hermes` (model resolved AFTER route picks the stage);
consume the dead `routing_for("research")["synthesis"]` key. `--no-route` opt-outs
on both commands, matching loop's pattern. Fable tier deferred by decision.

### ① Real token telemetry
Switch `AgentRunner` claude invocations to `--output-format json`; parse the result
envelope (`usage` input/output/cache tokens, `total_cost_usd`); write real actuals
into `costs.jsonl` + `trajectory.jsonl` steps. `cost.calibrate()` starts working;
`efficiency_report` gains an honest token axis (replace the "intentionally omitted"
caveat); routing ROI becomes measurable. Envelope parse failure degrades to today's
text path (fail-safe). Touches: `cli/runner.py`, `cli/trajectory.py`, `cli/cost.py`,
`cli/main.py`.

### ② Docs-check gate (`sigma docs-check`)
Generalize `claude_md_check`'s stale-count machinery into a cross-surface consistency
check: version parity (`cli/__init__.py` ↔ `.claude-plugin/plugin.json`), README badge
↔ real collected test count, PLAYGROUND.md counts, CLAUDE.md flag claims ↔ argparse
defaults. `--check` CI gate; wire into `doctor`. First run will FAIL on the known
drift (README badge 779, PLAYGROUND 232, CLAUDE.md 866 vs real 872; CLAUDE.md stale
on `--route`/worktrees) — fixing that drift is part of the feature's acceptance.
Touches: new `cli/docs_check.py` (pure) + `cli/docs_check_run.py` (thin), `cli/main.py`,
`cli/doctor.py`/`cli/checks.py`.

### ③ Lesson-efficacy loop (`sigma lessons`)
Record recalled lesson slugs per cycle (extend the recall block build in `run_loop`
to also emit slugs into the trajectory/events); pure projection correlating
lesson-recall with cycle outcomes: working (domain stopped re-failing), not-working
(recalled repeatedly, same topic keeps ratcheting), never-recalled (archive
candidates). Prune's evidence law: never delete, archive reversibly, surface only on
real evidence. Touches: `cli/skills_recall.py`, `cli/loop.py`, new `cli/lessons.py`,
`cli/main.py`.

### ④ Verifier context enrichment
`cmd_loop` already parses `spec_scenarios` once; pass the task's mapped scenario
(Given/When/Then) + a spec acceptance excerpt into `VERIFY_PROMPT` and
`LOGIC_PROMPT`, not just the e2e axis. Empty/no-scenario → prompts byte-identical
(fail-safe, regression-locked). Touches: `cli/loop.py` only.

### ⑤ Spec→eval autogeneration
Render `parse_scenarios(spec.md)` output into a `sigma/evals/<topic>.md` eval set
(scenario name → `## case:`, Then → rubric). New `sigma eval --from-spec <topic>`
(or generation step inside `/spec`). Eval becomes a standing regression net per
topic. Touches: `cli/scenarios.py` (render fn), `cli/eval_run.py`, `cli/main.py`,
`commands/spec.md`.

## Per-feature release discipline

Every feature that ships bumps `cli/__init__.py` + `plugin.json` together and updates
README.md + CLAUDE.md in the SAME change (existing release checklist). After ② lands,
`sigma docs-check --check` enforces this mechanically.
