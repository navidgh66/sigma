# Design: graphify-in-learn + `sigma scout` + `sigma prune`

**Date:** 2026-06-24
**Status:** approved (brainstorm → plan), ready to implement
**Branch:** `feat/graphify-scout-prune`

Three features land this round. They share one spine: each is an **external-power-tool
or context-hygiene layer** that the lean 3.9 CLI *shells out to* or *reads files for* —
never a new runtime import, never auto-destructive, always confirm-gated and fail-safe.
This is the same law that governs `rtk`, `caveman`, `statusline`, `cost`, and the
`chain.json`/`profile`/`gate` fail-safes already in the repo.

---

## Feature 1 — graphify always-on in `sigma learn` (+ bundled install)

### Goal
Every `sigma learn` builds a real dependency graph of the repo (graphify, local
tree-sitter, free) and feeds it to the learn agent, so `ARCHITECTURE.md` + the
`.tour` are grounded in extracted structure (call/import edges, god-nodes,
community clusters) instead of an eyeball read. graphify is bundled at install so
"present" is the happy path.

### The false blocker, corrected
`CLAUDE.md` says *"No graph engine — Graphify/tree-sitter need py3.10; we stay 3.9."*
That is true only for **importing** graphify into sigma's process. It does **not**
block sigma from **subprocessing** a standalone `graphify` binary installed in its
own isolated 3.10+ environment via `uv tool install graphifyy` (or `pipx`). sigma
already shells out to `claude`/`gemini`/`codex`/`rtk`/`caffeinate` exactly this way.
graphify is the same shape. **sigma stays 3.9 and dependency-light.**

The CLAUDE.md line must be rewritten to the import-vs-subprocess distinction or it
will mislead future work.

### Cost shape
graphify **code** extraction is local tree-sitter → **free, no API key, time-only**.
Only doc/PDF extraction needs an LLM backend. `graphify extract . --update` is
incremental (changed files only) → cheap on re-runs. So default always-on costs
wall-clock, not tokens, on a code repo.

### Always-on + fail-safe (both hold)
Every learn *attempts* the build. graphify present → build + inject. graphify absent
(user skipped onboard) → **warn + proceed without the graph**, never crash. Bundling
makes "present" the common case; fail-safe covers the edge. Matches the existing
missing-`chain.json`/`profile`/`gate` degradation law.

### Components
- **`cli/graphify.py` (NEW, pure + injectable)**
  - `graphify_status(which) -> {installed: bool}` — `which("graphify") is not None`.
  - `install_graphify(which, spawn) -> bool` — try `uv tool install graphifyy`, else
    `pipx install graphifyy`, else `pip install --user graphifyy`. Best-effort.
  - `setup_graphify(status_fn, confirm, which, spawn) -> bool` — confirm-gated,
    idempotent (no-op when already installed). RTK/caveman shape exactly.
  - `build_extract_argv(root) -> List[str]` → `["graphify", "extract", ".", "--update"]`.
  - `report_block(root, cap=...) -> str` — read `root/graphify-out/GRAPH_REPORT.md`,
    wrap in a labeled block; absent/unreadable → `""`; oversized → truncated to `cap`
    chars with a notice (same discipline as `skills_recall.render_recall_block`).
- **`cli/learn.py`** — `run_learn(..., build_graph: bool = True, graph_runner=None)`:
  if `build_graph` and graphify present, run `build_extract_argv` via an injected
  runner (best-effort; failure is logged into the result, never fatal). Then ALWAYS
  call `report_block(root)` and inject it into the learn prompt. Empty block → the
  prompt is **byte-identical to today** (regression-locked by test).
- **`cli/checks.py`** — `check_graphify(status_fn)`: present → OK; absent → WARN +
  confirm-gated install fix. **Never FAIL** (optional tool, like rtk/caveman). Added
  to `run_all`.
- **`cli/onboard.py`** — step 9: `setup_graphify` confirm-gated.
- **`cli/main.py`** — learn stays always-on; add `--no-graph` (skip build) and
  `--graph-backend <name>` (pass through for doc-heavy repos).
- **`installer/setup.sh`** — new best-effort step: `uv tool install graphifyy`
  (skip cleanly if neither uv nor pipx present). Renumber `[n/6]` → `[n/7]`.

### Risks
- MEDIUM — the absolute "no graph engine" CLAUDE.md line becomes wrong; rewrite precisely.
- LOW — build time on huge repos: mitigated by `--update`.
- LOW — graphify output drift: textual injection only, never parse structure.

---

## Feature 2 — `sigma scout`: keep the bundle fresh from skillsmp.com

### Goal
Query [skillsmp.com](https://skillsmp.com) (1.8M community skills), find skills
relevant to sigma's 9 domains + cross-cutting areas, **surface** ranked candidates,
and install on approval — so sigma's skill/plugin bundle stays current with a huge
upstream source instead of going stale.

### API (verified against `https://skillsmp.com/openapi.json`)
- `GET /api/v1/skills/search?q=<query>&category=<slug>&sortBy=stars|recent&page=&limit=`
- Response: `{success, data:{skills:[{name, description, author, githubUrl, skillUrl,
  stars, updatedAt}], pagination:{...}}, meta:{...}}`
- Auth: optional `Authorization: Bearer <key>` (anon 50 req/day; free key 500/day).
- `githubUrl` is the install handle (clone target).

### Lean transport
**stdlib `urllib.request` only** — no `requests` dependency (keeps the runtime
`pyyaml`+`rich`). API key → `~/.sigma/.env` as `SKILLSMP_API_KEY` via the existing
`cli/secrets.py` (never the committed config). An ambient env var counts as present.

### Components
- **`cli/scout.py` (NEW, pure)**
  - `domain_queries(domains) -> List[(domain, query, category)]` — map each sigma
    domain to a search term + skillsmp category slug.
  - `score_relevance(skill, domains) -> float` — keyword overlap with domain terms,
    boosted by stars + recency. Deterministic.
  - `dedup_against_bundle(skills, skills_dir) -> List[skill]` — drop any whose
    name/githubUrl already exists under `skills/` or `skills/vendor/`.
  - `rank(skills) -> List[skill]` — sort by score; cap; stable.
- **`cli/scout_run.py` (NEW, thin)**
  - `urllib` fetch wrapped fail-safe: API down / rate-limited / bad JSON → return
    empty + a banner, never crash.
  - Aggregate across domain queries, dedup, rank, **surface** the table.
  - On confirm, `git clone <githubUrl>` into the target dir.
- **`cli/main.py`** — `sigma scout`:
  - default → install into the current project's `.claude/skills/`.
  - `--vendor` → clone into sigma's own `skills/vendor/` (maintainer mode; you then
    commit it into the shipped bundle).
  - `--category <slug>`, `--recent` (sortBy=recent), `--dry-run`.
- **`commands/scout.md`** — `/scout` slash command.
- **`skills/sigma-scout/SKILL.md`** — the curation rubric: relevance to sigma's
  domains, quality bar (stars/recency), **license surfaced per candidate**, and the
  hard rule **never auto-install — a human picks** (mirrors contradiction flagging:
  surface, never auto-resolve).

### Decision (locked)
Both targets, flag-switched. Default = user project; `--vendor` = sigma bundle.

### Risks
- LOW — upstream API change: fail-safe degrade + a single typed parse point.
- LOW — license risk: surfaced per candidate, human approves; never auto-clones.
- LOW — rate limit: documented; respects `X-RateLimit-Daily-Remaining` header.

---

## Feature 3 — `sigma prune`: cut unused MCP/skills to save context + cost

### Goal
Loaded MCP servers + skills inject their tool schemas / descriptions into **every**
Claude context (a large, recurring token tax). `prune` inventories what's loaded,
estimates each item's context weight, cross-references recent actual usage, and
**surfaces** "heavy + unused" disable candidates. Disable is **reversible** (a list
in settings), never an uninstall.

### Signals (all read-only)
- Loaded set: `~/.claude/settings.json`, `~/.claude/plugins/installed_plugins.json`,
  and the project `.mcp.json`.
- Context weight: token estimate of each MCP's tool schemas / each skill's
  description, via the existing `cli/cost.py` estimator (no new estimator).
- Usage: scan recent session transcripts for actual tool/skill invocations within a
  `--days N` window.

### Components
- **`cli/prune.py` (NEW, pure)**
  - `parse_loaded(settings, plugins, mcp) -> Inventory` — every loaded MCP + skill.
  - `weigh(item) -> int` — token cost estimate.
  - `usage_from_transcripts(records, days) -> Dict[name, int]` — invocation counts.
  - `rank_candidates(inventory, usage, weights) -> List[Candidate]` — heavy + unused
    first; an item used recently is never a candidate regardless of weight.
- **`cli/prune_run.py` (NEW, thin)** — read the files + transcripts, build the report,
  **surface** the ranked candidates; on confirm write a **disabled set** into
  settings via an **immutable merge** (new dict, preserve every other key — exactly
  like `cli/statusline.py`). Reversible: re-enable removes the entry.
- **`cli/main.py`** — `sigma prune`: `--check` (read-only report, CI exit-code),
  `--yes` (apply without prompting), `--days N` (usage window, default e.g. 14).
- **`commands/prune.md`** — `/prune` slash command.
- **`skills/sigma-prune/SKILL.md`** — the pruning rubric: a distinct **context-saving**
  layer that *composes* with RTK (proxy token cut), caveman (output terseness), and
  sigma-cost (the ledger) — it **never duplicates** them. Disable ≠ delete.

### Decision (locked)
Reversible disable only. Never uninstall.

### Risks
- LOW — disabling something still needed: reversible, and recently-used items are
  excluded from candidacy by construction.
- LOW — settings corruption: immutable merge, never mutate the loaded dict; fail-safe
  on unreadable settings (empty inventory, no write).
- MEDIUM — transcript format/location assumptions: isolate parsing behind one
  function; missing/garbled transcripts → "unknown usage" (treated conservatively as
  "used", so we never prune on absent data).

---

## Conventions (all three)
- Python 3.9 type hints (`Optional[X]`/`List[X]`, never `X | None`).
- stdlib-first; no new runtime deps (`urllib` for scout, file reads for prune).
- Pure logic separated from subprocess/network/file IO; everything injectable +
  testable with fakes. No real subprocess, network, or settings.json touched in tests.
- All agent/model invocation passes prompts via argv, never the shell.
- TDD: write the failing test first for each pure function, then implement.
- 419 existing pytest tests stay green; ruff clean (py39 target).
