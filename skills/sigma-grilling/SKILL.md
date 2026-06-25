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
costs a rewrite (Lee Boonstra — *Spec-Driven, Production-Grade Development in the
Age of Vibe Coding*).

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

### 7. Singular requirements (ISO/IEC/IEEE 29148 — *singular*)
- Any criterion hiding TWO behaviours in one line ("…and…", "…also…", "…as well as…")?
  → split into separate criteria. Conjoined requirements get half-implemented.
- Each acceptance criterion expresses exactly ONE testable outcome.

### 8. Error-path coverage (EARS unwanted-behaviour pattern)
- Each operation that can fail has ≥1 explicit `IF <trigger> THEN the system SHALL …`
  criterion. The EARS error pattern is a structural edge-case checklist — a risky
  operation with only happy-path criteria → HIGH (missing error path).
- Maps onto axis 4; this axis demands the coverage be *present*, not just enumerable.

### 9. Cross-artifact traceability (chain check, not single-doc)
- Every requirement maps to ≥1 downstream task; every task traces back to a requirement.
- Flag zero-coverage requirements (will silently not get built) + orphaned tasks
  (built but unmotivated → scope creep). Use the chain context (`chain.json`) when grilling
  a spec that already has `tasks.md`.

### 10. Constitution (MUST invariants — higher-order gate)
- A persistent set of project MUST-principles the artifact may NOT violate, independent
  of the per-finding axes: ML leakage/splits discipline, maker ≠ checker separation, no
  secrets in committed config, fail-safe defaults (default-deny verdicts, default-WAKE gate).
- A constitution violation is **CRITICAL** regardless of how small it looks.

### 11. Behaviour-orientation (anti context-dump)
- Is the artifact behaviour-oriented (testable criteria) or long prose / a context dump?
  Agents demonstrably *ignore* prose — a spec that reads like a brief, not a contract,
  → HIGH. Reward self-enforcing, testable statements over narrative.
- **Scale-adaptive rigor**: a one-file change is not a multi-PR system; demand depth
  proportional to blast radius, not uniform ceremony.

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

## Output contract — per-axis decomposed scoring

Grade each axis **separately**, then derive the overall verdict mechanically. A holistic
"this spec looks risky" judgment correlates far worse with expert review than per-criterion
grading with evidence (decomposed criteria-based eval ≈ 2× the expert correlation of a single
holistic score) — and the per-axis breakdown is the calibration signal a panel can vote on.

1. One **AXIS** line per interrogated axis (skip axes the artifact genuinely doesn't touch):
```
AXIS | <axis-name> | <PASS|FAIL>
```
2. One **FINDING** line per issue (EXACTLY this shape — same as `/review`):
```
FINDING | <CRITICAL|HIGH|MEDIUM|LOW> | <artifact section/anchor> | <one-line issue + what to add/decide>
```
3. The **overall verdict** as the FINAL line (derived, not vibes):
```
VERDICT: READY  or  VERDICT: BLOCK
```

Derivation (mechanical): any axis FAIL with a CRITICAL/HIGH finding → overall **BLOCK**.
READY only when no axis carries a CRITICAL/HIGH. The final `VERDICT:` line is what the gate
parses (`hermes._grill_ready`) — AXIS/FINDING lines never substitute for it.

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
