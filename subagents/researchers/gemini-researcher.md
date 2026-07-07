---
agent: gemini-researcher
model: gemini
role: researcher
mode: cli-dispatch
---

# Gemini Researcher — real CLI dispatch template

This file is NOT a persona to roleplay. It is the argv template and
output-cleaning instructions `/research` follows to dispatch the REAL Gemini
CLI as a subprocess via the Bash tool, when `gemini` is available locally.

## Dispatch

```
gemini -p "<brief>" --output-format json
```

Substitute `<brief>` with the research brief for the current topic and depth
mode (see `commands/research.md`'s Depth modes section for the wording rules).

## Cleaning the output

The CLI emits a JSON envelope. Extract the response text:
- Newer CLIs: `{"response": "..."}` — use that string directly.
- Older/alternate shape: dig into `candidates[].content.parts[].text` and
  concatenate.
- If neither shape parses, fall back to the raw stripped text rather than
  discarding output.

This mirrors `cli/models.py`'s `_clean_gemini` logic — keep the two in sync if
either changes.

## Fallback (CLI not found locally)

If `which gemini` fails, `/research` dispatches THIS file's persona instead —
as an explicit, visible approximation, never silently substituted:

You are a research subagent leaning into Gemini's typical strengths: broad
web recall, freshness, large-context synthesis. Investigate the given topic
and return raw findings (data for aggregation, not a human-facing message).

## Return

<!-- sigma:research-rules:start -->
- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
<!-- sigma:research-rules:end -->
