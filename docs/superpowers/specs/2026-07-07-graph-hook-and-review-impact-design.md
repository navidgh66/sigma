# Design: graphify post-commit hook wiring + graph-aware review diff-impact

**Date:** 2026-07-07
**Status:** approved (brainstorm) → ready for plan
**Origin:** external-repo review (openwiki auto-docs PR, Understand-Anything `/understand-diff`).
Both external ideas already have upstream homes in **graphify** (which sigma already
shells out to via `cli/graphify.py`); this design *wires* graphify's capabilities into
sigma rather than reinventing them.

---

## Context

Reviewing three repos for ideas to bundle:
- **openwiki** — auto-maintained agent docs. Overlaps `sigma learn`; its only novel bit
  is a scheduled refresh. graphify already ships `graphify hook install` (post-commit +
  post-checkout, AST-only, 0 API cost, plus a `graph.json` git merge-driver) — a strictly
  better local version. → **wire it, don't rebuild it.**
- **Understand-Anything** — `/understand-diff` = diff-impact-on-knowledge-graph. graphify's
  `graphify prs <PR#>` covers the *GitHub-PR* case; sigma review's *local-diff* mode (the
  default) is the gap. → **new additive Impact section in `sigma review`.**
- **claude-video** — wrong domain (media), no hook point. Skipped.

sigma stays **Python 3.9** and **never imports graphify** (it needs 3.10+); it only
SHELLS OUT to the `graphify` binary and reads graphify's output files with stdlib `json`.
Both features are **fail-safe**: graphify absent, or its artifacts missing/unreadable,
degrades to today's behavior byte-for-byte.

---

## Feature 1 — wire `graphify hook install` (post-commit graph refresh)

### Decision
Don't author sigma's own git hook. graphify's `graphify hook install` already does exactly
the graph-only, no-API-cost post-commit rebuild we want, **plus** a `graph.json` merge
driver that sigma's own hook could not easily provide. sigma adds a thin, confirm-gated,
idempotent wrapper — the exact shape of `setup_graphify` / `setup_rtk` / `setup_caveman`.

### Components
All new code lives in `cli/graphify.py` (the existing graphify seam) + one probe + one
onboard step.

1. **`graphify_hook_status(root, which=shutil.which) -> Dict`** (pure-ish; stats FS only)
   - Returns `{"installed": bool}`.
   - `installed` is True when the repo's `.git/hooks/post-commit` exists **and** contains a
     graphify marker (grep the file for the string `graphify` — graphify embeds an
     interpreter path + `graphify` invocation in the hook it writes).
   - Fail-safe: no `.git`, no hook file, unreadable → `{"installed": False}`. Never raises.

2. **`install_graphify_hook(root, which, spawn) -> bool`**
   - Runs `graphify hook install` with `cwd=root` via the injected `spawn` (reuse the
     module's `_default_spawn`). Returns True on exit 0.
   - Precondition: graphify binary present (caller checks). Never raises (spawn is
     OSError-guarded like `install_graphify`).

3. **`setup_graphify_hook(status_fn=None, confirm=None, which=None, spawn=None, root=None) -> bool`**
   - Confirm-gated + idempotent, mirroring `setup_graphify`:
     - graphify binary **absent** → no-op, return False (nothing to hook; install graphify
       first — surfaced in the note).
     - hook already installed (`graphify_hook_status`) → no-op, return False.
     - else → `confirm(...)`, then `install_graphify_hook`.
   - `confirm` defaults to `lambda msg: False` (same default-deny as siblings).
   - All lookups/spawns injectable so tests never touch git or spawn a process.

4. **`cli/checks.py`: `check_graphify_hook(...)`** — WARN-never-FAIL probe (like
   `check_graphify`). OK when installed; WARN with a fix `("install the graphify
   post-commit hook", _fix)` where `_fix` calls `setup_graphify_hook(confirm=lambda _:True)`.
   Gated on graphify being installed — if graphify itself is absent, the probe returns a
   WARN that points at installing graphify first (no duplicate FAIL). Registered in
   `run_all_checks` right after `check_graphify`.

5. **`cli/onboard.py`: new step** after the existing graphify-install step (~line 117):
   only offered when graphify is installed; `setup_graphify_hook(confirm=confirm)`; on
   change print `"  ✓ graphify post-commit hook installed — graph refreshes on each commit"`.

### Non-goals
- No sigma-authored hook script, no merge-driver logic (graphify owns both).
- No change to `sigma learn` (the graph is still built there; the hook just keeps it fresh).
- `doctor --check` stays read-only (the probe reports; the fix is confirm-gated as usual).

---

## Feature 2 — graph-aware diff impact in `sigma review`

### Decision
Add an **informational "Impact" section** to the review report listing, per changed file,
which graph nodes it defines and which other nodes depend on them (reverse edges). This is
**additive only**: the gate (`review.gate`) is untouched and **no axis prompt changes**
(explicit user choice). No graph → no section, report byte-identical to today.

### Components

1. **New pure module `cli/graph_impact.py`** (stdlib `json` only; sigma stays 3.9):

   - **`load_graph(root, max_bytes=...) -> Optional[dict]`**
     - Reads `root/graphify-out/graph.json`. Returns the parsed dict, or `None` on:
       missing file, unreadable, invalid JSON, or size over `max_bytes` (a cap like
       `graphify.report_block`'s `_DEFAULT_REPORT_CAP`, but byte-sized — a big graph must
       not blow memory/report). Never raises.

   - **`impact_for(graph, changed_files) -> List[FileImpact]`**
     - `FileImpact` = `@dataclass(frozen=True)` with `file: str`, `nodes: List[str]`
       (node names/ids defined in that file), `dependents: List[str]` (node names with an
       edge whose target is one of `nodes`).
     - **Schema-tolerant** (graphify's `graph.json` schema is not a stable contract):
       - nodes: try `graph["nodes"]`; each node may carry its source path under any of
         `file` / `path` / `source` / `source_file` (first present wins). Match against a
         changed file when the node path **equals or ends with** the changed path (handle
         absolute vs repo-relative). Node label from `name` / `id` / `label`.
       - edges: try `graph["edges"]` (or `links`); endpoints under `source`/`target` (or
         `from`/`to`), which may be node ids or names — resolve through a node-id→name map
         built from the nodes pass.
       - Any missing/oddly-shaped key → that item is skipped, never a crash. If nothing
         resolves, every `FileImpact` has empty lists (still returned, so the section can
         say "no graph nodes matched the changed files").
     - Deterministic order: input `changed_files` order; nodes/dependents sorted + deduped.
     - Caps: `nodes`/`dependents` truncated to a per-file limit (e.g. 20) with a
       "+N more" note, same discipline as the recall/report caps.

   - **`render_impact_section(impacts) -> str`**
     - Markdown block: `## Impact (knowledge graph)` heading, one bullet per file with
       matched nodes → their dependents. A short preamble line noting this is derived from
       graphify's `graph.json` and is informational (does not affect the gate). Empty
       `impacts` (or all-empty) → a single "_No graph nodes matched the changed files._"
       line (only rendered when a graph was loaded at all).

2. **Wire into `cli/review_run.py`** (~after `render_report`, before writing):
   - `graph = load_graph(root)`. If `graph is not None`:
     `report = report + "\n" + render_impact_section(impact_for(graph, change.files))`.
   - Guarded so an impact failure never breaks a completed review (wrap in the same
     best-effort spirit as the existing report-write try/except; an exception → skip the
     section, log nothing fatal).
   - **Untouched:** `rv.gate`, `rv.build_axis_prompt`, ratcheting, PR comment, cost record.

### Non-goals
- No graph feeding any axis prompt (user chose report-section-only).
- No new dependency; no graphify import; no call to `graphify query/path` subprocess
  (we read the already-built `graph.json` directly — cheaper, offline, deterministic).
- No gate/verdict change — Impact is never blocking.

---

## Testing (both features)

pytest, matching the repo's fake-injection style (663-test suite must stay green, ruff clean).

**Feature 1** (`tests/test_graphify.py` additions):
- `graphify_hook_status`: installed marker present / absent / no `.git` / unreadable.
- `setup_graphify_hook`: graphify-absent no-op; already-installed no-op; confirm-denied
  no-op; confirm-approved → spawn called with `["graphify","hook","install"]` + cwd=root.
- `check_graphify_hook`: OK when installed, WARN when not, WARN when graphify absent.

**Feature 2** (`tests/test_graph_impact.py` new):
- `load_graph`: happy parse; missing file → None; bad JSON → None; oversize → None.
- `impact_for`: canonical schema (`nodes`/`edges`, `source`/`target`); alt schema
  (`links`, `from`/`to`, `path`); id-vs-name edge endpoints resolved; no match → empty
  FileImpacts; endpoint into a changed node surfaces as a dependent; cap/truncation.
- `render_impact_section`: non-empty render shape; graph-loaded-but-no-match line;
  determinism (stable order).
- `review_run` integration (fake AgentRunner + a temp `graphify-out/graph.json`): report
  gains the Impact section; **no `graph.json` → report byte-identical to the no-graph run**
  (the key regression lock, mirroring `test_no_graph_prompt_byte_identical_to_baseline`).

---

## Conventions honored
- Python 3.9 type hints (`Optional[X]`/`List[X]` from `typing`, never `X | None`).
- Pure logic (`graph_impact`, the `graphify` status/render fns) separated from subprocess
  (`review_run`, `onboard`, `install_*`) — testable with fakes.
- Fail-safe degradation everywhere (the graphify-seam discipline): absent/broken → today's
  behavior, never a crash, never a silent gate change.
- Confirm-gated + idempotent + immutable-merge for anything touching shared state
  (the hook install is delegated to graphify, so no settings.json write of our own).
- New files stay small (<400 lines) and single-purpose.
