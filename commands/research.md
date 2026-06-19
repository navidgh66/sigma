---
command: /research
description: Multi-model parallel research (Claude + Gemini + GPT) into a single cited research.md; supports web-grounded and deep (exhaustive) depth modes
stage: 1
inputs: ["topic"]
outputs: ["sigma/specs/{date}-{slug}/research.md"]
---

# /research

Run **multi-perspective parallel research** on a topic and synthesize one cited
document. In-session this fans out to **parallel Claude Code subagents** — no
terminal needed. (The CLI `sigma research` instead fans out to three real model
CLIs via subprocess; this command is the in-session equivalent.)

## Behavior

1. Take the research `topic`.
2. **Dispatch researcher subagents in parallel** — send them in a SINGLE message
   (multiple Task/Agent tool calls in one turn) so they run concurrently, each
   with the same brief but a distinct lens from `subagents/researchers/`:
   - **claude-researcher** — deep reasoning, code-aware synthesis, nuanced
     trade-off analysis.
   - **gemini-researcher** — broad web recall, freshness, large-context synthesis.
   - **gpt-researcher** — alternative recall + reasoning, cross-check coverage.

   Give each subagent the persona body from `subagents/researchers/<name>.md` and
   the topic. Each returns RAW findings (data for aggregation, not prose for the
   user): themed findings with source URLs, a confidence note per theme, and
   explicit flags on single-source / unverified claims. Prefer sources from the
   last 12 months.
3. **Aggregate** the returned findings: dedupe overlapping claims, cross-reference
   across researchers (a claim found by only one is `unverified`), prefer recent
   sources.
4. Write `research.md` with: executive summary, themed findings with inline
   citations, per-researcher contribution notes, key takeaways, source list, gaps.

## Depth modes

Match the CLI's three depths (`sigma research` / `--web` / `--deep`):

- **default** — researchers may answer from knowledge; cite what they assert.
- **web** (asked for "web" / "current" / "look it up) — each researcher MUST use
  its web-search / grounding tools and cite real, resolvable URLs it actually
  consulted; do not answer from memory alone. Keep it a quick pass.
- **deep** (asked for "deep" / "exhaustive" / "thorough research") — same web
  mandate, but exhaustive: multiple searches per theme, more sources, stronger
  cross-checking, every theme web-grounded. Slower by design.

When unsure which depth, ask once; otherwise default.

## Rules

- Every claim cites a source. No unsourced assertions.
- Separate fact from inference; label projections / opinions.
- State which researchers ran (and any that returned nothing — no silent caps).
- Keep the main context clean — researchers run as subagents; only their
  aggregated findings return to the main thread.
- Dispatch the subagents concurrently (one message, multiple Task calls), not
  one after another.

## Next

→ `/propose`
