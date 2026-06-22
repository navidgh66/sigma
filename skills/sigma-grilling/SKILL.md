---
name: sigma-grilling
description: >
  Adversarially grill a sigma design (architecture.md) or specification (spec.md)
  BEFORE the pipeline advances to code — catch logic flaws, ambiguity, untestable
  acceptance criteria, missing edge/error paths, scope creep, and ML/data risks
  while they still cost a sentence to fix instead of a rewrite. Use when running
  /grill, when a human or the loop wants to pre-flight a spec or blueprint, when
  about to decompose a spec into tasks, or when the user asks to "review",
  "pressure-test", "stress-test", "red-team", or "poke holes in" a design/spec.
  Carries the interrogation rubric; the griller is a separate agent from the author.
origin: sigma
---

# sigma-grilling

The **grilling rubric** — what a skeptical reviewer interrogates in a design or
spec before any code is written. Grilling is the cheap gate: a flaw caught here
costs a sentence; the same flaw caught after the agent generates a thousand lines
costs a rewrite (Boonstra, 2026 — *Spec-Driven Production-Grade Development*).

**Two laws (non-negotiable, sigma-wide):**
- **Maker ≠ griller** — the griller is a *distinct agent* from the artifact's
  author. No self-grading (same separation `cli/loop.py` enforces).
- **Default to BLOCK on doubt** — an inconclusive or silent grill is never READY
  (skeptical, like `_verdict_pass`). Demand evidence; quote the exact line.

## When to grill what

| Target | Artifact | Gate position | Emphasis |
|--------|----------|---------------|----------|
| **blueprint** | `architecture.md` | after `/blueprint`, before `/spec` | boundaries, coupling (CACE), risks, missing components, data flow |
| **spec** | `spec.md` | after `/spec`, before `/tasks` | ambiguity, testable criteria, edge/error paths, ML contracts |

## The axes — interrogate each

### 1. Ambiguity
- Any requirement that reads two ways? → force ONE reading, state it.
- Undefined / overloaded terms ("fast", "the service", "reliable")? → define or quantify.
- Junior-dev test: could a literal-minded agent implement this wrongly-but-defensibly? If yes, it's ambiguous.

### 2. Hidden assumptions — **pre-mortem**
- "Assume this shipped and failed in production. List 10 reasons why." For each, what spec clarification prevents it?
- Inherited/stale requirements carried over without re-checking?
- Optimistic assumptions: zero integration bugs, perfect data, dependency always up?

### 3. Testability
- Is **every** acceptance criterion measurable AND falsifiable? Untestable criterion → BLOCK.
- Bad: "model should be accurate." Good: "macro-F1 ≥ 0.82 on the held-out test split, measured by `eval.py`."
- Does each criterion map to a concrete check (test, metric, command)?

### 4. Edge cases & error paths
- Only the happy path described? Enumerate failure scenarios explicitly.
- **Boundary values**: empty input, single element, max size, off-by-one, null, zero, negative.
- Dependency-down, timeout, partial failure, retry/idempotency — handled or named?

### 5. Scope
- Explicit **out-of-scope** section present? If missing → BLOCK (scope is undefined).
- Any "small add-on" smuggling in real complexity / a hidden core dependency?
- YAGNI: speculative features that aren't required by the goal → cut.

### 6. ML / data risk (load the domain `logic-evaluator.md` via sigma-domains)
- **Leakage**: target/anachronistic features, row duplication across splits, group leakage.
- **Split discipline**: time-series split by time (not random)? Stratification where needed?
- **Train/serve skew**: serving features defined the same as training? Logged + compared?
- **Metric correctness**: metric matches the objective (class imbalance, ordering variance)?
- **Determinism**: seeds pinned, eval reproducible?

## Spec-quality checks (from the whitepaper — a *good* spec)

- **BDD scenarios**: are acceptance criteria expressed as Scenario / Given / When /
  Then (State → Action → Outcome)? Are edge cases their own scenarios? Missing
  behavioral scenarios for a user-facing flow → HIGH.
- **"Why behind the what"**: is the rationale/background present so the agent can
  reason forward — not just the *what*?
- **Pinned versions**: are libraries / models given explicit version numbers?
  (Agents fall back to stale training-cutoff versions otherwise.)
- **Full technical design**: data schemas + API contracts ("the contracts that let
  parts talk"), not just prose.
- **Format / token discipline**: deeply nested config (>3 levels) rendered as flat
  YAML, narrative as Markdown — not heavy nested JSON in prose (the "format tax").

## Output contract

Findings, one per line, EXACTLY:
```
FINDING | <CRITICAL|HIGH|MEDIUM|LOW> | <artifact section/anchor> | <one-line issue + what to add/decide>
```
Then `VERDICT: READY` or `VERDICT: BLOCK`.

Severity guide:
- **CRITICAL** — a flaw that, if built, breaks correctness or safety (leakage,
  untestable core criterion, undefined scope, contradictory requirements).
- **HIGH** — a real gap likely to cause rework (missing error path, ambiguous
  core behavior, no BDD scenario for a user flow).
- **MEDIUM** — should fix (missing version pins, thin rationale).
- **LOW** — polish (format/token economy, wording).

Gate: **BLOCK on any CRITICAL/HIGH or an inconclusive grill.** READY only when clean.

## Rules

- Don't rewrite the artifact — name the flaw and what must be decided/added.
- Quote the exact ambiguous/untestable line as evidence.
- Load only the domain(s) the artifact actually touches (lean context).
- A CRITICAL/HIGH a human overrides is recorded in the grill report, never silent.
