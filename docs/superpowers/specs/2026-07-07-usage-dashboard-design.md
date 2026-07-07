---
title: sigma usage — thin wrapper around ccusage for Claude Code token/cost visibility
date: 2026-07-07
status: approved
---

# `sigma usage`: token/cache/cost dashboard via ccusage

## Problem

There is currently no way to see aggregate Claude Code token usage (input,
output, cache read, cache write, cost) across sessions/projects from inside
sigma. `cli/cost.py` tracks a distinct, unrelated thing — sigma's own heavy-op
estimates (review/loop/research token budgets, recorded into
`sigma/costs.jsonl`) — not Anthropic's real session usage data.

Claude Code already writes every session's token accounting to local JSONL
files (`~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl`, one line per
turn, `message.usage` carrying `input_tokens`, `output_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`). Verified live
against this machine's own session log during research — the schema is real,
not just documented.

**ccusage** ([ccusage.com](https://ccusage.com/guide/)) is a mature,
actively-maintained, local-only, read-only CLI that already parses this exact
tree (plus Codex, Gemini CLI, and a dozen other coding-agent formats) into
daily/weekly/monthly/session reports with cost estimates from a maintained
model-pricing table. Zero-install via `npx ccusage@latest`.

## Goals

- Give sigma a `sigma usage` entry point to this data, discoverable alongside
  `sigma cost` (which reports something different — sigma's own op ledger).
- Reuse ccusage rather than re-deriving JSONL parsing + a pricing table.
- Never require Node/npx as a hard sigma dependency — degrade gracefully.

## Non-goals

- No bundling/vendoring ccusage into the sigma repo.
- No re-rendering ccusage's output through sigma's own Rich tables — ccusage's
  tables are already good; passthrough keeps sigma's side trivial.
- No sigma-side pricing table or JSONL parsing — ccusage owns both.
- No auto-install of Node/npx.

## Design

### Command shape

```bash
sigma usage                  # → npx -y ccusage@latest  (ccusage's own default view)
sigma usage claude session    # → npx -y ccusage@latest claude session
sigma usage --json            # → passthrough; still raw ccusage JSON output
```

Every argument after `usage` passes straight through to ccusage unmodified.
sigma adds zero flags of its own — ccusage's own docs remain the docs for this
command; no flag surface to keep in sync.

### Modules

```
cli/usage.py       NEW.
  node_runtime_available(which=shutil.which) -> bool
      True if `npx` or `bunx` is on PATH. Mirrors statusline.py's
      identical check (same reasoning: ccusage runs via npx).
  build_argv(passthrough_args) -> List[str]
      ["npx", "-y", "ccusage@latest", *passthrough_args] — pure, no I/O.

cli/main.py         MODIFIED.
  cmd_usage(args) -> int:
      if not node_runtime_available(): print fail-safe message, return 0.
      else: return spawn(build_argv(args.usage_args))  # inherits stdio,
            passthrough exit code (spawn injectable for tests, same
            pattern as statusline.py's _default_spawn).
  New subparser: `usage`, accepts `nargs=argparse.REMAINDER` for
  passthrough args (so `sigma usage claude session --json` forwards
  `claude session --json` verbatim to ccusage).

cli/checks.py       + check_usage_tool(which=...) -> Check
  WARN-never-FAIL, mirrors check_graphify's shape exactly: missing
  npx/bunx is optional-tool-absent, not a doctor failure.
```

### Error handling (fail-safe, matches statusline.py / graphify.py convention)

- No npx/bunx on PATH → print `"npx not found — install Node.js to use
  'sigma usage' (wraps ccusage: https://ccusage.com)"`, return 0. Never
  crashes; `sigma doctor`'s `check_usage_tool` surfaces the same gap as an
  optional WARN, not a failure.
- npx present but ccusage itself errors (bad flag, no data found yet, network
  hiccup on first `npx` fetch) → passthrough ccusage's own stderr and exit
  code unmodified. sigma does not intercept or reinterpret ccusage's errors.

### Testing

- `cli/usage.py`: `node_runtime_available` with an injected `which` returning
  None/a path (present/absent both covered, mirrors
  `statusline.statusline_status`'s existing test shape); `build_argv` asserts
  exact prepend + unmodified passthrough args, no mutation.
- `cmd_usage`: injected fake spawn capturing the argv it was called with,
  asserts passthrough args reach it unchanged; asserts the fail-safe path
  returns 0 and never calls spawn when node_runtime_available() is False.
- `check_usage_tool`: same WARN-never-FAIL assertion shape as the existing
  `test_check_graphify_*` tests.

## Rollout

1. `cli/usage.py` (node_runtime_available + build_argv), unit tests.
2. `cmd_usage` + `usage` subparser in `cli/main.py` (REMAINDER passthrough
   args), unit tests with injected spawn.
3. `check_usage_tool` in `cli/checks.py`, wired into `sigma doctor`'s check
   list, unit test.
4. Manual verification: run `sigma usage` locally, confirm it produces
   ccusage's real daily report against this machine's actual
   `~/.claude/projects/` data.
5. Full test suite green, ruff clean.

## Open questions / risks

- ccusage's own maintenance/uptime is an external dependency risk — if the
  npm package is ever unpublished or renamed, `sigma usage` degrades to the
  same "tool not found"-shaped error ccusage itself would report, not a
  sigma crash (thin wrapper means thin blast radius).
- First run pays an `npx` download cost (a few seconds) if `ccusage@latest`
  isn't already cached locally — acceptable, matches ccstatusline's existing
  same-shaped tradeoff in `cli/statusline.py`.
