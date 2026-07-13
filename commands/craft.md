---
command: /craft
description: Craft a design/plan into verified implementation — drives spec → grill → tasks → loop from an artifact you already have
stage: aux
inputs: ["a design/plan/big-spec you provide (pasted, a file path, or an existing architecture.md)"]
outputs: ["sigma/specs/{date}-{slug}/spec.md", "tasks.md", "impl/", "verify/"]
---

# /craft

You already have a design, plan, or big spec. `/craft` is the **back-half
conductor**: it takes that artifact as the starting point and drives the
implementation half of the pipeline for you —

```
spec → grill → tasks → (implement → verify)  loop
```

— instead of making you run each stage by hand. It is the in-session sibling of
`sigma hermes --auto` (which chains the WHOLE pipeline from `research`); `/craft`
starts from a design you bring, so it skips `research → propose → blueprint`.

Use `/craft` when: you arrive with a design/plan/RFC/big-spec in hand and want it
turned into verified, working code. Do NOT use it to start from a blank idea —
that's `/research` → … or `hermes --auto`.

## Input

The design can arrive three ways — accept whichever the user gives:

1. **Pasted** into the chat alongside the invocation.
2. **A file path** (e.g. `/craft docs/my-design.md`) — read it.
3. **An existing `architecture.md`** already in the spec workspace — use it as-is.

If none is present, STOP and ask for the design. `/craft` never invents the
design itself — that is the human's contribution to this flow.

## Behavior

Run these stages in order, in-session, each loading its domain context-engine
(via the `sigma-domains` skill). Persist each artifact under
`sigma/specs/{date}-{slug}/` so the chain is inspectable and resumable.

1. **Seed** — resolve the design (above). If it isn't already
   `architecture.md` in the workspace, write it there verbatim as the blueprint
   artifact so downstream stages read it as context. Slugify a short topic name
   for the workspace dir if one doesn't exist.
2. **`/spec`** — turn the design into an implementation-ready `spec.md`, with
   **BDD `Scenario / Given / When / Then` acceptance criteria** (these become the
   contract for grill, tasks, `--e2e`, and the verify/logic axes).
3. **`/grill`** (`--target spec`) — adversarially pressure-test the spec BEFORE
   any code (maker ≠ griller). On a **BLOCK** (CRITICAL/HIGH logic flaw), STOP
   and surface it for human review — do not proceed to tasks. This gate is the
   whole point of crafting from a design instead of vibe-coding it.
4. **`/tasks`** — decompose `spec.md` into a domain-routed `tasks.md` with
   `[scenario: <name>]` tags mapping tasks to their acceptance scenarios.
5. **`/loop`** — run the full-axis maker→checker cycles over `tasks.md`
   (logic + simplify + advisor + e2e on by default), ratcheting failures into
   `skills/`.

## Gates (stop for a human, don't barrel through)

- **grill BLOCK** — a CRITICAL/HIGH flaw in the spec. Fix the design/spec, then
  re-run from `/grill`. (Mirrors `hermes --auto`'s `grill-blocked` gate.)
- **spec approval** — after `/spec` (and a clean grill), pause so the human can
  read `spec.md` before code is generated. Proceed on confirmation.
- **verify FAIL that survives advisor escalation** — a real bug the loop
  couldn't self-correct; surface it rather than marking the task done.

Honor these like `hermes`: a gate is a stop, not a speed bump.

## Rules

- The design is the human's input; `/craft` never fabricates it.
- Every stage is a DISTINCT agent from the prior one (maker ≠ checker ≠ griller
  holds across the chain, same as the manual stages).
- `spec.md` is the source of truth; `tasks.md`, `impl/`, `verify/` are derived.
- Keep context lean — each stage loads only the domain(s) its work needs.
- Resumable: if a stage's artifact already exists, offer to reuse it rather than
  clobbering (same overwrite discipline as `sigma learn`).

## Relationship to other commands

- `hermes --auto` — full pipeline from `research`; `/craft` = its back half from
  a design you already have.
- `/spec`, `/grill`, `/tasks`, `/loop` — the individual stages `/craft` chains;
  run them by hand for finer control or to resume mid-chain.
- `sigma loop` — the terminal stage only (needs `tasks.md`); `/craft` produces
  that `tasks.md` for it.

## Next

→ after the loop settles: `/verify`, `/review`, or `sigma weave` to export the
artifact chain.
