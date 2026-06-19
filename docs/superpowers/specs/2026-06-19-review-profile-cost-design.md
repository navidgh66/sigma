# Design: Team-Change Review + Logic Profile + Cost Loop

**Date:** 2026-06-19
**Status:** Approved (brainstorm complete)
**Scope:** Three coordinated additions to sigma — a three-axis review module for
team-authored changes, a logic-invariant profile that grounds it, and a cost
estimate/measure loop for sigma's heavy operations.

---

## Motivation

sigma's existing review capability (`/verify` + per-domain `logic-evaluator.md` +
the loop's maker→checker→logic axes) binds to sigma's **own** pipeline — it grades
artifacts sigma generated, against a spec sigma wrote. It does not review
**team-authored changes** on a real ML codebase, and its review criteria are
**static** hand-written per-domain markdown.

For ML-heavy systems the important logic lives in the code (loss functions, data
splits, feature pipelines, reward shaping, eval metrics) *and* in the engineering
(control flow, data contracts, concurrency, state, API boundaries). Reviewing team
diffs needs criteria that stay current as the codebase and its logic change.

This design adds:

1. **`/profile` + `sigma profile`** — a living record of the system's invariants
   (ML-logic **and** system-logic), refreshed manually, staleness-flagged.
2. **`/review` + `sigma review`** — a three-axis reviewer (code / ML-logic /
   system-logic) of a change set (local diff or PR), grounded in the profile +
   ratcheted lessons, that gates on CRITICAL/HIGH and ratchets findings back into
   `skills/`.
3. **`sigma-cost`** — an estimate-before / measure-after closed loop for sigma's
   heavy ops, recommending model routing and surfacing token sinks.

## Design decisions (from brainstorm)

| # | Decision |
|---|----------|
| Q1 | Review targets **both** PR (`gh pr diff`) and local git diff/branch. |
| Q2 | Criteria evolve via **profile (what the system is) + ratcheted lessons (what the team keeps getting wrong)** — both injected into review. |
| Q3 | Profile built by a **dedicated `/profile` pass** (build=B); freshness is **staleness-flagged** (fresh=2): warn if profile older than touched files, proceed anyway. |
| Q4 | **Three axes**, each a distinct agent: ① code ② ML-logic ③ system-logic. |
| Q5 | Output **C** (markdown always + PR summary comment in PR mode) / verdict **3** (findings always; gate fails only on CRITICAL/HIGH) / **X** (CRITICAL/HIGH findings ratchet to `skills/`). |
| Q6 | **Both surfaces** (C): plugin slash commands primary + steerable; CLI for autonomous + parallel fan-out + CI gate. Shared pure core in `cli/`. |
| Q7 | Cost skill = **D** (estimate-then-measure closed loop), both bundled skill + CLI wiring. |

## Principles preserved

- **Maker ≠ checker** → the 3 review axes must be distinct agent instances
  (enforced with `ValueError`, like `execute_cycle`).
- **Skeptical verdicts** → a missing/inconclusive axis verdict does NOT pass.
- **Fail-safe degradation** → missing profile / empty diff / absent `gh` /
  garbage ledger never hard-blocks (mirrors verify's `chain.json` fallback and the
  gate-defaults-WAKE inverse).
- **Pure logic separated from subprocess** → everything testable with fakes.
- **Plugin-first** → slash commands are primary; CLI keeps only what CC can't do
  in-session (true parallel fan-out, autonomous runs, CI exit codes).
- **Reuse, don't rebuild** → `loop.ratchet_to_skills`, `loop._verdict_pass`,
  `skills_recall`, `domains_index`, `paths.DOMAINS`, `runner.AgentRunner`, the
  per-domain `logic-evaluator.md` files.
- **py3.9 type hints** → `Optional[X]` / `List[X]`, never `X | None`.

---

## Architecture

### Surfaces

| Surface | Command | Role |
|---------|---------|------|
| Plugin | `/profile` | In-session walker → `sigma/profile/logic-profile.md`. |
| Plugin | `/review [target]` | In-session 3-axis review; steerable. |
| CLI | `sigma profile` | Autonomous walker (AgentRunner). |
| CLI | `sigma review [target]` | Parallel 3-axis fan-out + `--check` CI gate (exit 1 on CRITICAL/HIGH). |
| CLI | `sigma cost` | Report the cost ledger. |

### Pure core (cli/, testable, no subprocess)

- **`cli/review.py`**
  - `ChangeSet` resolution contract (files + hunks; local-diff vs PR shapes).
  - `Finding` dataclass (axis, file, line, severity, message).
  - per-axis prompt builder (injects diff + profile + recalled lessons + staleness banner).
  - `aggregate(findings)` — dedup by `(file, line, message)`.
  - `gate(findings)` — FAIL if any severity in {CRITICAL, HIGH}.
  - `infer_domains(paths, profile)` — reuse `paths.DOMAINS` + `domains_index`; default `ai-agent-engineering`.
  - axis-distinctness guard (raise `ValueError` if a runner is reused across axes).
- **`cli/profile_manifest.py`**
  - `logic-profile.md` skeleton contract (ML-logic section + system-logic section).
  - `staleness(profile_path, touched_files)` — compare profile mtime/hash vs files; returns a banner string or empty.
- **`cli/cost.py`**
  - `estimate(op, inputs)` → `CostEstimate` (per-axis token estimate + model-tier recommendation).
  - `record(...)` contract → one append line for `sigma/costs.jsonl` (timestamp passed in by caller — projection stays deterministic, mirrors `events.Event.ts`).
  - `calibrate(ledger_rows)` — adjust factors from recent est-vs-actual deltas; fall back to static factors on missing/garbage ledger.
  - `report(ledger_rows)` — trends, per-op spend, biggest sinks, routing suggestions.

### Thin wiring (cli/, subprocess)

- `cli/review_run.py` — `AgentRunner` wiring for `sigma review`: parallel 3-axis fan-out (ThreadPoolExecutor, like `research`), distinct runner per axis.
- `cli/profile_run.py` — `AgentRunner` wiring for `sigma profile` walker.

### Slash commands

- `commands/review.md` — resolve change set (`git diff` / `gh pr diff`), load profile + recall + staleness, dispatch 3 distinct reviewer subagents, aggregate, write report, PR-comment, ratchet.
- `commands/profile.md` — walk repo, emit `logic-profile.md` (both sections).

### Bundled skill

- `skills/sigma-cost/SKILL.md` — in-session: read `costs.jsonl`, advise model routing + recommend RTK/caveman when waste detected, report trends.

### Reused per-domain context

The existing `context-engines/<d>/verifiers/logic-evaluator.md` files supply the
ML-logic axis criteria — applied to the **diff against the profile**, not to a
sigma-generated artifact. No new per-domain files.

---

## Data flow — `/review`

```
/review [PR# | URL | empty=local diff]
  → resolve change set            git diff | gh pr diff        [in-session]
  → load profile + recalled lessons + staleness check          [cli.review, cli.profile_manifest — pure]
  → cost estimate (advisory) printed up front                  [cli.cost — pure]
  → dispatch 3 reviewer subagents (code / ML-logic / system)   [in-session; CLI = parallel]
  → aggregate + dedup findings by file:line                    [cli.review — pure]
  → gate: FAIL if any CRITICAL/HIGH                             [cli.review — pure]
  → write sigma/reviews/{date}-{slug}/review.md
  → PR mode: post summary comment (gh)                         [in-session]
  → ratchet CRITICAL/HIGH findings → skills/                   [loop.ratchet_to_skills — existing]
  → cost record appended to costs.jsonl                        [cli.cost — pure contract]
```

## The three axes

Each is a distinct subagent, same context bundle, different lens:

- **Axis 1 — Code review.** Bugs, security, quality, conventions. Severity-tagged.
- **Axis 2 — ML-logic review.** Reuses per-domain `logic-evaluator.md` ML criteria
  (splits/leakage/metrics/reward/eval-determinism) applied to the diff vs profile.
  Flags broken ML invariants, introduced leakage, silent metric shifts.
- **Axis 3 — System-logic review.** Control-flow termination, data-contract/schema
  breaks, concurrency/state coherence, API-boundary compatibility, failure handling.

Shared context injected into all three: change set (hunks + enough surrounding
code), `logic-profile.md`, recalled lessons for inferred domain(s), staleness banner.

## Cost loop — `sigma-cost`

```
estimate(op, inputs)  →  advisory (per-axis tokens + model-tier rec)   [before]
   run op ...
record(op, axes, models, tokens, est)  →  append costs.jsonl           [after]
calibrate(recent rows)  →  sharpen estimate factors                    [next time]
report(rows)  →  trends, sinks, routing suggestions                    [sigma cost]
```

Wired into `/review`, `/profile`, `sigma review/profile/loop/research`. Fail-safe:
missing/garbage ledger → static factors, never blocks. Boundary: RTK reduces tokens
at the proxy; caveman trims output; sigma-cost estimates/measures/routes sigma's own
heavy stages and may *recommend* RTK/caveman — composes, no duplication.

---

## Error handling (fail-safe)

| Condition | Behavior |
|-----------|----------|
| Empty/missing diff | Exit clean: "nothing to review". Not a failure. |
| Missing profile | Proceed profile-less with warning (lessons + diff only). |
| Stale profile | Warn banner, proceed (Q3=2). |
| Reviewer axis dies | That axis = inconclusive; does NOT pass. Gate treats missing verdict as non-passing (skeptical). |
| `gh` absent / not a PR | PR-comment no-ops; markdown still written. |
| Ratchet contradiction | Flagged via existing `find_contradictions`; never auto-resolved. |
| Axis runners not distinct | `ValueError` (maker≠checker analog). |
| Missing/garbage `costs.jsonl` | Estimator falls back to static factors; op proceeds. |

---

## Testing

Pure logic → fakes, no real agents. Target the existing 80%+ / pure-separated discipline.

- `tests/test_review.py` — diff parsing, domain inference, aggregation/dedup, gate
  (CRITICAL/HIGH → fail), prompt building includes profile+recall, fail-safe paths
  (no profile, empty diff), axis-distinctness `ValueError`.
- `tests/test_profile_manifest.py` — staleness check (profile vs touched-file
  hashes), skeleton contract validation.
- `tests/test_cost.py` — estimate math, calibration from ledger, report shape,
  fail-safe (no/garbage ledger).

All new tests must keep the suite green and ruff clean (py3.9 target).

---

## File layout (new)

```
cli/review.py              pure: change-set contract, per-axis prompt build, aggregate+dedup, gate, domain infer, axis-distinctness
cli/profile_manifest.py    pure: logic-profile skeleton + staleness(profile, files)
cli/cost.py                pure: estimate / record contract / calibrate / report
cli/review_run.py          thin: AgentRunner wiring for `sigma review` (parallel 3-axis)
cli/profile_run.py         thin: AgentRunner wiring for `sigma profile` walker
commands/review.md         /review slash command (in-session 3-axis)
commands/profile.md        /profile slash command (in-session walker)
skills/sigma-cost/SKILL.md in-session cost advisor + reporter
tests/test_review.py
tests/test_profile_manifest.py
tests/test_cost.py
```

`cli/main.py` gains `review`, `profile`, `cost` subcommands. CLAUDE.md + PLAYGROUND.md updated.

## Out of scope (YAGNI)

- No standing daemon / webhook server (PR review is invoked, not event-driven).
- No new per-domain markdown (reuse `logic-evaluator.md`).
- No dashboard/telemetry beyond the `costs.jsonl` ledger + `sigma cost` report.
- No auto-resolution of profile↔code drift or skill contradictions (humans decide).
```
