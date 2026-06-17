---
command: /hermes
description: Conductor — route a plain-language request to the right sigma pipeline stage and run it, single-step or auto-chained
---

# /hermes

The **conductor**. You describe what you want in plain language; Hermes figures
out which pipeline stage to run next and drives it. Additive — `/research`,
`/spec`, etc. all still work standalone.

> Full execution engine lives in the CLI: `sigma hermes "<msg>" --topic <t>`.
> This command is the in-session equivalent — follow the same logic by hand.

## Behavior

1. **Route (hybrid).**
   - **State-driven (default, free):** inspect the spec workspace
     `sigma/specs/{date}-{slug}/`. Pick the next stage by which artifacts exist
     (no `research.md` → research; has `spec.md`, no `tasks.md` → tasks; …).
   - **Intent override:** if the message signals a jump ("redo research",
     "skip to verify", names a stage), route there instead.
2. **Inject the stage's skill.** brainstorming (propose/blueprint),
   writing-plans (spec), TDD (implement-task), systematic-debugging +
   verification-before-completion (verify). Add caveman if the user wants terse.
3. **Run the stage** (follow that stage's command), write its artifact.
4. **Record** an event (task/stage/status) for the board and a line in
   `hermes-log.md`.

## Modes

- **Single-step (default):** run ONE stage, show the result, stop. Wait for the
  human to approve the next hop.
- **Auto (`--auto` in CLI):** chain stages until a **human gate**
  (spec-approval, verify-failed), a stage failure, or the hop budget.
- **Terse:** compress output via the caveman skill.

## Guardrails

- Never replace the human at a gate — stop at spec approval and on verify FAIL.
- Maker ≠ checker still holds for any stage Hermes runs.

## Next

→ `/board` to see task state · `/loop` to run autonomous cycles
