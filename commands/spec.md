---
command: /spec
description: Write a detailed, self-contained specification with interfaces, schemas, and acceptance criteria
stage: 4
inputs: ["sigma/specs/{date}-{slug}/architecture.md"]
outputs: ["sigma/specs/{date}-{slug}/spec.md"]
---

# /spec

Write the **implementation-ready specification**.

## Behavior

1. Read `architecture.md`.
2. Produce `spec.md` with:
   - Goal and scope (and explicit **out-of-scope**)
   - The **"why behind the what"** — rationale/background so the implementer can
     reason forward, not just the *what*.
   - Component specs: signatures, data schemas, config, error handling
   - For ML: data contracts, feature definitions, model interface, eval protocol
   - **Acceptance criteria as BDD scenarios** (see below) — testable, measurable
   - Verification steps per component
   - Named files to create/modify
   - Pinned **version numbers** for libraries / models (agents otherwise fall back
     to stale training-cutoff versions).

## Acceptance criteria → BDD (Behavior-Driven)

Express each acceptance criterion as a **Scenario / Given / When / Then** block
(State → Action → Outcome). This turns vague intent into criteria an agent can
build to without guessing, and feeds `/grill` and `--tdd` directly:

```gherkin
Scenario: <behavior name>
  Given <starting state / inputs>
  When <action>
  Then <measurable, falsifiable outcome>
```

Cover the happy path AND give edge cases their own **named** scenarios:

```gherkin
Scenario: null input rejected
  Given no input is provided
  When the endpoint is called
  Then a 400 error is returned with a clear message

Scenario: dependency unavailable
  Given the downstream service is down
  When the action is attempted
  Then the system fails gracefully with a logged error (no data loss)
```

A user-facing flow with no behavioral scenario is an incomplete spec. Each
scenario becomes a direct test target (TDD) and a review contract — `/verify`
and `/review` check that every scenario is demonstrably covered in the code.

## Format / token discipline

The spec is a compiled instruction set, not just docs — every char is budget +
latency. Keep **narrative in Markdown**; render **deeply nested config (>3
levels) as flat YAML**, not heavy nested JSON in prose (avoids the "format tax").

## Rules

- Self-contained: a fresh agent can implement from this alone.
- No ambiguity — if a requirement has two readings, pick one and state it.
- No placeholders / TBD.

## Next

→ `/grill --target spec` (grill it before decomposing) → `/tasks`
