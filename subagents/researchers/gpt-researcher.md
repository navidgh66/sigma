---
agent: gpt-researcher
model: gpt
role: researcher
mode: cli-dispatch
---

# GPT Researcher — real CLI dispatch template

This file is NOT a persona to roleplay. It is the argv template and
output-cleaning instructions `/research` follows to dispatch the REAL Codex
CLI (ChatGPT-subscription-backed) as a subprocess via the Bash tool, when
`codex` is available locally.

## Dispatch

```
codex exec --sandbox read-only --color never "<brief>"
```

For deep/web mode, append: `-c tools.web_search=true` — enables Codex's
built-in web_search tool for real grounding.

Substitute `<brief>` with the research brief for the current topic and depth
mode (see `commands/research.md`'s Depth modes section for the wording rules).

## Cleaning the output

`codex exec` prints session/event preamble interleaved with the agent's
actual reply. Drop lines starting with `[timestamp] ...` event markers and
metadata lines (`workdir:`, `model:`, `provider:`, `approval:`, `sandbox:`,
`reasoning:`, `tokens used:`, `session id:`, `user instructions:`, `--------`),
keep everything else. This mirrors `cli/models.py`'s `_clean_codex` logic —
keep the two in sync if either changes.

## Fallback (CLI not found locally)

If `which codex` fails, `/research` dispatches THIS file's persona instead —
as an explicit, visible approximation, never silently substituted:

You are a research subagent leaning into alternative-recall and reasoning
strengths for cross-checking coverage. Investigate the given topic and return
raw findings (data for aggregation, not a human-facing message).

## Return

<!-- sigma:research-rules:start -->
- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
<!-- sigma:research-rules:end -->
