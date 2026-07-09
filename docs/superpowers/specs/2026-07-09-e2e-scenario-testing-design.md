# Design: `/e2e` — Executable BDD Scenario Testing

**Date:** 2026-07-09
**Status:** approved for planning

## Problem

sigma's `/spec` already writes acceptance criteria as BDD `Scenario / Given /
When / Then` blocks (`commands/spec.md`). `/verify` and `/review` already check
"scenario coverage" — but that check is an LLM **reading code** and reasoning
whether a scenario is satisfied. Nothing actually **runs** the scenario against
a live instance of the target app. A scenario can read as "covered" while the
real user flow is broken.

This closes that gap: make the Given/When/Then contract **executable**, and
wire it into both the manual pipeline (`/implement-task`) and the autonomous
loop (`sigma loop`), not just as a standalone command.

## Non-goals

- No new scenario-authoring format. Scenarios are read from `spec.md` — the
  existing BDD blocks are the single source of truth. A parallel scenario file
  would drift from the spec.
- No actor/judge split within a scenario. One agent drives Given→When and
  checks Then — mirrors how a human tester works a scenario end to end.
- Not a generic browser/API test-generation tool. No static Playwright/pytest
  files are generated or maintained; each run drives the scenario live.

## Three surfaces

### 1. `commands/tasks.md` — plumbing (prerequisite for the other two)

`tasks.md` currently lists "acceptance criteria" per task but does not name
which `spec.md` `Scenario:` block(s) that task is responsible for. Add a
**Scenarios** field per task: the exact `Scenario:` name(s) from `spec.md` this
task must satisfy (may be empty — not every task has a user-facing flow, e.g.
a pure backend utility task). This is what lets `/implement-task` and
`sigma loop` look up "just this task's scenario" instead of the whole spec.

### 2. `/e2e` — standalone command (stage: aux, plugin-only)

```yaml
command: /e2e
description: Run spec.md's BDD scenarios end-to-end against a live instance of the target app
stage: aux
inputs: ["sigma/specs/{date}-{slug}/spec.md"]
outputs: ["sigma/specs/{date}-{slug}/e2e-report.md"]
```

**Behavior:**

1. Resolve the workspace: no argument → the most recently modified
   `sigma/specs/{date}-{slug}/` directory containing a `spec.md` (same
   "latest workspace" convention `loop`/`hermes` use).
2. Extract every `Scenario: / Given / When / Then` block from `spec.md`.
3. **Launch the app** — invoke the existing `run` skill (already in the skill
   bundle: "Launch and drive this project's app to see a change working").
   It detects whether the app is already live and starts it if not.
4. For each scenario, one agent:
   - Performs **Given** (sets up starting state) and **When** (the action) —
     using whatever tool fits the target: browser automation (Playwright /
     chrome-devtools MCP) for a web UI, HTTP calls (curl/requests) for an
     API, subprocess invocation for a CLI. sigma is domain-general (9
     domains, not web-only) — the tool choice is inferred from the scenario
     text and the project, not hardcoded.
   - Checks **Then** and assigns a verdict:
     - `PASS` — ran to completion, Then held.
     - `FAIL` — ran to completion, Then's assertion was false. A real
       behavior bug.
     - `ERROR` — could not complete Given/When (app unreachable, tool
       crash, timeout). Inconclusive — NOT a behavior verdict.
5. Write `sigma/specs/{date}-{slug}/e2e-report.md`:
   one row per scenario — name | verdict | evidence (screenshot ref /
   response body / stdout excerpt) — plus an overall summary.
6. **Ratchet**: every `FAIL` (never `ERROR` — no lesson from absent evidence,
   the same law `sigma prune` follows) writes a lesson via the exact
   `/sigma-learn-lesson` format (domain-tagged), so `sigma loop` and
   `/implement-task` recall it next time in that domain.

**Next:** all PASS → ship · any FAIL → fix impl (lesson already ratcheted),
re-run `/e2e` · any ERROR → fix the environment (app unreachable / tool
issue), re-run.

### 3. `/implement-task` — add an e2e step after the TDD test-exists step

After the existing TDD flow (test-writer pens failing test → implementer makes
it pass), and after the implementer's own note-writing step, add:

> **4b. If this task has a mapped Scenario in `tasks.md`**: run it end-to-end
> the same way `/e2e` does (launch via the `run` skill if not already live,
> drive Given/When, check Then). Record the verdict in `impl/{task_id}.md`.
> A `FAIL` here means the task is not actually done — do not consider the
> task complete until the scenario passes (an `ERROR` — environment issue —
> does not block completion, but must be noted and retried before verify).

This runs **once per task**, only for tasks with a mapped scenario — not the
full spec suite, so completing task 5 doesn't re-run task 1's flow.

### 4. `cli/loop.py` — new optional gate axis, mirrors `logic_checker`

Add an optional `e2e_runner: Optional[AgentRunner] = None` parameter to
`execute_cycle`, following the exact shape of `logic_checker`:

- **Distinctness**: `e2e_runner` must be distinct from implementer, verifier,
  logic_checker, test_writer, simplifier, and advisor — `ValueError` on reuse
  (`is`, not `==`), same law as every other axis.
- **When it runs**: after `_run_verify` (verify + logic) passes, only when
  the current task has a mapped scenario in `tasks.md` (looked up via the new
  Scenarios field from surface #1). No mapped scenario → e2e step is skipped
  entirely, not scored.
- **Gate semantics**: this is a GATE, not advisory (unlike the post-pass
  simplifier). A cycle only reaches `outcome.verified = True` if verify AND
  logic AND e2e all pass — same "no silent pass on an inconclusive axis" law
  `review.py`'s gate already enforces.
  - `FAIL` → cycle fails: ratchets a lesson (`verify failed: {title}` path,
    reusing the existing ratchet call), blocks, same as a logic FAIL today.
  - `ERROR` → does **not** flip an otherwise-passing cycle to FAIL. Logged
    to `CycleOutcome.notes` and the loop log, but not ratcheted (no lesson
    from absent evidence — mirrors `gate.py`'s own asymmetry: skeptical
    default-FAIL on real assertions, fail-safe default-continue on
    infrastructure breakage).
- **New `CycleOutcome` field**: `e2e_ok: Optional[bool] = None` — `None` when
  no `e2e_runner` given or the task had no mapped scenario (byte-identical to
  today when unused); `True`/`False` on PASS/FAIL; stays `None` on `ERROR`
  (inconclusive, distinct from a scored False).
- **Advisor interaction**: if `advisor` is also provided, an e2e FAIL
  escalates through `_run_advisor_escalation` exactly like a verify/logic
  FAIL does today — the advisor doesn't need to know which axis failed, only
  the failure reason/detail, which the e2e step supplies in the same
  `(reason, detail)` shape `_run_verify` returns.
- **`--route` wiring**: e2e role routes like `logic` (reasoning-heavy tier),
  not the mechanical tier — driving a live app and judging Then requires the
  same reasoning strength as the logic evaluator.

A bare `execute_cycle()` call with `e2e_runner=None` is byte-identical to
today's behavior — this is a strict, opt-in addition.

## Report format (`e2e-report.md`)

```markdown
# E2E Report — {workspace slug}

| Scenario | Verdict | Evidence |
|---|---|---|
| user signs up | PASS | screenshot: signup-success.png |
| null input rejected | FAIL | expected 400, got 500 — see response.json |
| dependency unavailable | ERROR | app unreachable on :3000 after 30s |

**Summary:** 1 PASS / 1 FAIL / 1 ERROR — not clean.
```

## Testing

- `cli/loop.py`: unit tests for `execute_cycle` with a fake `e2e_runner` —
  distinctness `ValueError` cases, PASS/FAIL/ERROR gate behavior, skip-when-
  no-mapped-scenario, ratchet-on-FAIL-not-on-ERROR, advisor escalation on an
  e2e FAIL, `--route` tier assignment.
- `commands/e2e.md`, `commands/implement-task.md`, `commands/tasks.md`: no
  Python to unit test (markdown command templates) — verified by a manual
  dry-run once implemented, same as other command docs.

## Open risk

Live-app e2e steps cost real wall-clock + tokens per cycle. This is
acknowledged, not solved here: the design accepts the cost because a FAIL gate
is only as good as its evidence, and `--route`-ing e2e to a cheaper tier isn't
appropriate (judging Then needs full reasoning). Users who find this too slow
for every cycle can simply not pass `--e2e` (opt-in flag, to be named in the
implementation plan) and rely on `/e2e` run manually instead.
