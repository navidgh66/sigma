---
command: /research
description: Multi-model parallel research (Claude + Gemini + GPT) into a single cited research.md
stage: 1
inputs: ["topic"]
outputs: ["sigma/specs/{date}-{slug}/research.md"]
---

# /research

Run **multi-model deep research** on a topic and synthesize one cited document.

## Behavior

1. Take the research `topic` (and optional `--models claude,gemini,gpt`; default: all available).
2. Spawn researchers **in parallel** (subprocess), each with the same brief:
   - `claude -p` → Claude researcher subagent
   - `gemini` CLI → Gemini researcher subagent
   - `openai` CLI → GPT researcher subagent
   - Skip any model whose CLI is missing; log which were skipped (no silent caps).
3. Each researcher returns: findings, sources (URLs), and a confidence note.
4. **Aggregate**: dedupe overlapping claims, cross-reference (flag single-source
   claims as unverified), prefer sources from the last 12 months.
5. Write `research.md` with: executive summary, themed findings with inline
   citations, per-model contribution notes, key takeaways, source list, gaps.

## Rules

- Every claim cites a source. No unsourced assertions.
- Separate fact from inference; label projections/opinions.
- State which models ran and which were skipped.
- Keep the main context clean — researchers run as subagents/subprocesses.

## Next

→ `/propose`
