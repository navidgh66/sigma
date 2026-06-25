---
name: sigma-prune
description: >
  Find loaded-but-unused MCP servers and plugins that bloat every Claude context,
  and reversibly disable the dead weight to save tokens + cost. Use when the context
  feels heavy, tool lists are huge, or you want to trim what's loaded. Triggers:
  "too many tools", "context is bloated", "what MCP/plugins am I not using", "save
  context", "prune unused", "sigma prune", or a periodic context-hygiene pass.
origin: sigma
---

# sigma-prune

Trim the recurring context tax. Every enabled plugin + connected MCP server injects
its tool schemas / skill descriptions into **every** turn; unused ones are pure
overhead. The pure inventory/usage/ranking logic lives in `cli/prune.py`; the file
reads + reversible write in `cli/prune_run.py`. This skill is the judgment layer.

## What counts as a candidate
- **Loaded** — an enabled plugin (`enabledPlugins`) or a connected MCP server
  (user `~/.claude.json` or project `.mcp.json`).
- **Idle** — zero `tool_use` / `Skill` invocations in the usage window (default: all
  scanned transcripts; narrow it with `--recent-files N` to prune servers idle
  *lately* even if heavily used long ago).
- **Ranked by REAL context weight.** A server's weight scales with its *distinct tool
  count* (schema width, observed across history), not a flat per-kind constant — a
  100-tool server dwarfs a 2-tool one instead of ranking identical. Unknown tool count
  → conservative per-kind fallback.
- **Rarely-used = low-confidence (opt-in).** `--idle-threshold N` also surfaces items
  used ≤N times, flagged `⚠ rarely used` — a judgment call for the human, never an
  auto-disable. Default 0 = unused-only (unchanged).

## Two non-negotiable laws
1. **Never prune on absent evidence.** No transcripts to scan → surface nothing.
   Missing usage data is treated as "used", not "unused" — the conservative default
   (the inverse of guessing, mirroring gate-defaults-WAKE / verdict-defaults-FAIL).
2. **Reversible, never destructive.** Disable = flip `enabledPlugins[name]=false` via
   an immutable settings merge (every other key preserved, like statusline). The
   item stays installed on disk. Re-enable = flip it back. User-level MCP servers in
   `~/.claude.json` are surfaced for a **manual** edit — prune never auto-edits that
   file.

## When to keep something unused
- It's a **safety/just-in-case** tool you reach for rarely but critically.
- It was only just installed (no usage *yet* ≠ unused).
- Disabling it would break an active workflow in another project (settings.json is
  global — a plugin idle here may be hot elsewhere). Prefer project-scoped judgment.

## Compose, don't duplicate
Bundle-hygiene trio: `sigma-scout` grows the bundle, **sigma-prune trims it**,
`sigma-cost` sizes the token cost of carrying it. Orthogonal to RTK (proxy token
cut) and caveman (output terseness) — prune cuts *input/context* weight, the layer
neither of those touches.

## Flags
`--check` (read-only CI gate, exit 1 on bloat), `--yes` (disable all prunable
plugins), `--files N` (transcript scan = schema width), `--recent-files N` (usage
window — prune items idle in the last N), `--idle-threshold N` (also surface items
used ≤N times as low-confidence). Default is confirm-per-item, unused-only.
