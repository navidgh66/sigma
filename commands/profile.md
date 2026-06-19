---
command: /profile
description: Walk the codebase and persist its logic invariants as sigma/profile/logic-profile.md (grounds /review)
stage: aux
inputs: []
outputs: ["sigma/profile/logic-profile.md"]
---

# /profile

Build the **logic profile** — a living record of this codebase's invariants that
`/review` reads as grounding. Two parts: **ML-logic** (splits, leakage guards,
metrics, losses, reward shaping, eval determinism, train/serve consistency) and
**system-logic** (control-flow contracts, data contracts/schemas, concurrency &
shared-state rules, API boundaries, failure handling).

Read the project from its root, then write `sigma/profile/logic-profile.md` with
EXACTLY these two headers (verbatim), nothing else:

```
## ML-logic invariants
<each invariant points at a real file; state it as something a change must not
silently break>

## System-logic invariants
<each invariant points at a real file; state it as a contract a change must keep>
```

## Notes
- Be concrete: every invariant names real code. Prefer a short true list over a
  long speculative one.
- Refresh after meaningful logic changes — `/review` flags the profile **stale**
  when it is older than the files under review (it warns, never blocks).
- Both sections are mandatory; an empty section is a profile bug.

## Next
→ `/review` (the profile now grounds the three review axes)
