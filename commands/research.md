---
command: /research
description: Multi-model parallel research (real Gemini/GPT CLI dispatch + Claude-side deep-research skill), MCP search-tool grounding, and manual findings — synthesized into one cited research.md
stage: 1
inputs: ["topic"]
outputs: ["sigma/specs/{date}-{slug}/research.md"]
---

# /research

Run **multi-perspective parallel research** on a topic and synthesize one cited
document, using REAL model diversity and REAL search grounding — not personas
roleplaying as other models.

## Behavior

1. Take the research `topic`.
2. **Claude-side deep research** — invoke the `deep-research` skill directly
   (it already uses firecrawl/exa MCP tools for grounded, cited findings).
   This replaces dispatching a "claude-researcher" persona subagent — that
   persona ran on the SAME model already running this session, so it added no
   real capability beyond a self-instruction. `deep-research` does real work.
3. **Real Gemini/GPT dispatch via Bash** — check CLI availability first
   (`which gemini`, `which codex` via the Bash tool). If found, invoke the
   REAL CLI as a subprocess:
   ```
   gemini -p "<brief>" --output-format json
   codex exec --sandbox read-only --color never "<brief>"
   ```
   using the brief + argv template described in `subagents/researchers/
   gemini-researcher.md` / `gpt-researcher.md`. Clean the raw output using the
   same rules those files describe (gemini JSON-envelope extraction, codex
   event-noise stripping — matching `cli/models.py`'s `clean_output` logic).
   If a CLI is NOT found locally, fall back to dispatching that persona as a
   Task subagent instead, but say so explicitly: "gemini CLI not found locally
   — using Claude-side approximation, not real Gemini." Never silently
   substitute persona output for real model output.
4. **MCP search-tool dispatch** — if a web-search MCP tool is connected in
   this session (any tool whose name matches a search/web-search pattern —
   e.g. `mcp__firecrawl__firecrawl_search` — not hardcoded to one vendor),
   call it directly as an additional research source, dispatched in parallel
   with steps 2-3. Treat its results as grounded findings (real, resolvable
   source URLs) on the same footing as the other sources.
5. **Manual findings** — check `sigma/specs/{date}-{slug}/manual/*.md` for
   any pre-completed findings a human dropped in before or during this run.
   Fold each file in as an additional source, same rules as everything else.
6. **Synthesize**: cross-reference ALL returned findings (deep-research skill
   output, real CLI dispatch output, persona-fallback output if used, MCP
   search-tool output, manual findings): dedupe overlapping claims, promote
   claims confirmed by 2+ sources, flag single-source claims as unverified,
   prefer recent sources.
7. Write `research.md` with: executive summary, themed findings with inline
   citations, per-source contribution notes (including which sources ran vs.
   were unavailable), key takeaways, source list, gaps.

## Depth modes

Match the CLI's three depths (`sigma research` / `--web` / `--deep`):

- **default** — sources may answer from knowledge; cite what they assert.
- **web** (asked for "web" / "current" / "look it up) — each source MUST use
  its web-search / grounding tools and cite real, resolvable URLs it actually
  consulted; do not answer from memory alone. Keep it a quick pass.
- **deep** (asked for "deep" / "exhaustive" / "thorough research") — same web
  mandate, but exhaustive: multiple searches per theme, more sources, stronger
  cross-checking, every theme web-grounded. Slower by design.

When unsure which depth, ask once; otherwise default.

## Rules

<!-- sigma:research-rules:start -->
Every researcher/tool follows the same rules:

- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
<!-- sigma:research-rules:end -->

- State which sources ran (real CLI dispatch vs. persona fallback vs. skipped)
  — no silent caps, and never present a persona-fallback reply as if it were
  the real model.
- Keep the main context clean — dispatched work runs as subagents/Bash calls;
  only aggregated findings return to the main thread.
- Dispatch steps 2-4 concurrently where possible (Bash calls + Task subagent
  calls + MCP tool calls in one message), not one after another.

## Next

→ `/propose`
