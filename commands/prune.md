---
command: /prune
description: Surface loaded-but-unused MCP servers + plugins (context-token bloat) and reversibly disable the dead weight — never uninstall
stage: aux
inputs: ["~/.claude/settings.json (enabledPlugins)", "~/.claude.json (mcpServers)", "project .mcp.json", "recent session transcripts (usage)"]
outputs: ["a ranked report", "reversible enabledPlugins=false writes (on approval)"]
---

# /prune

Every enabled plugin and connected MCP server injects its tool schemas / skill
descriptions into **every** Claude context — a recurring token tax. Prune finds the
**loaded-but-unused** ones and reversibly disables them.

## How it runs
1. Inventory what's loaded: plugins (`enabledPlugins` in `~/.claude/settings.json`),
   user MCP servers (`mcpServers` in `~/.claude.json`), and project MCP (`.mcp.json`).
2. Estimate each item's context weight (MCP servers carry many tool schemas →
   heaviest; plugins lighter). Reuses the cost estimator's static-factor discipline.
3. Scan recent session transcripts for actual `tool_use` / `Skill` invocations.
4. Rank **unused** items, heaviest first. **Anything used recently is kept.**

## The two safety laws
- **Conservative on missing evidence.** No transcripts found → prune surfaces
  nothing (it never guesses an item is unused without proof).
- **Reversible, never destructive.** Disabling flips `enabledPlugins[name]=false`
  via an immutable settings merge (every other key preserved). The plugin stays
  installed; re-enable anytime. User-level MCP servers are *surfaced for a manual
  edit* — prune never edits `~/.claude.json` automatically.

## Flags
- `--check` — read-only report; exit 1 if prunable bloat exists (CI gate).
- `--yes` — disable all prunable plugins without prompting.
- `--files N` — how many recent transcripts to scan (default 40).

## Compose, don't duplicate
Distinct layer of bundle hygiene: `scout` *grows* the bundle, **prune *trims* it**,
`sigma-cost` *sizes* the token cost, RTK cuts proxy overhead, caveman trims output.

## Next
→ disable the dead weight · restart Claude Code · re-enable any plugin later by
flipping its `enabledPlugins` flag back to true.
