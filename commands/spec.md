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
   - Component specs: signatures, data schemas, config, error handling
   - For ML: data contracts, feature definitions, model interface, eval protocol
   - **Acceptance criteria** (testable, measurable)
   - Verification steps per component
   - Named files to create/modify

## Rules

- Self-contained: a fresh agent can implement from this alone.
- No ambiguity — if a requirement has two readings, pick one and state it.
- No placeholders / TBD.

## Next

→ `/tasks`
