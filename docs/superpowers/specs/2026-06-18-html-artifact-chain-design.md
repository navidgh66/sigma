# Design: HTML Artifact Chain (`sigma weave`)

**Date:** 2026-06-18
**Status:** Approved (all sections)
**Topic:** Weave sigma pipeline stage artifacts into one self-contained HTML chain
(human review + cross-session handoff) plus a machine manifest the verify stage
consumes for full-chain review.

## Motivation

Inspired by Anthropic's "unreasonable effectiveness of HTML" post: pipeline stage
artifacts woven into one navigable HTML chain a later session/agent can read
whole. sigma already produces per-stage markdown artifacts and already has
`sigma-present` (markdown→HTML deck/report/kanban). What is missing is the
**chain**: linking research→propose→blueprint→spec→tasks→verify into one
cross-linked HTML whole + a machine index.

This is **hybrid mode**: markdown stays the engine's source of truth; HTML is a
derived woven view for humans AND a sidecar JSON manifest is a machine index the
verify stage reads for full-chain review.

## Core Invariant (non-negotiable)

Markdown is the engine's single source of truth. Agents write `.md`; stage
chaining stays `.md`; `loop.py` keeps parsing `tasks.md`. The HTML chain and JSON
manifest are **always derived, never authoritative**. Deleting
`chain.html`/`chain.json` leaves the pipeline fully functional.

## Section 1 — Architecture

Two new modules, mirroring existing sigma patterns:

- **`cli/weave.py`** — orchestrator, agent-driven via `AgentRunner` (mirrors
  `cli/learn.py`). Scans the spec workspace for whichever stage artifacts exist,
  builds a prompt embedding them + a chain spec, calls `claude -p` to emit one
  self-contained `chain.html`. Also triggers the pure manifest writer.
- **`cli/weave_manifest.py`** — pure logic (mirrors `cli/board.py` /
  `cli/codetour.py`). `build_manifest(workspace)` → manifest dict (deterministic,
  0 tokens, fully unit-testable). `validate_chain_html(html, expected_stages)` →
  list of problems (well-formedness + every present stage has a section). The
  non-determinism guard for agent HTML output.

```
weave.py (orchestrator)
 ├─ weave_manifest.build_manifest()  → chain.json   [pure, 0 tokens]
 ├─ AgentRunner.run(prompt+artifacts) → chain.html   [agent, designed]
 └─ weave_manifest.validate_chain_html()              [pure guard]
```

Two outputs, two engines: `chain.json` = pure Python (trustworthy, testable);
`chain.html` = agent (rich/designed). The manifest never depends on the agent
succeeding.

## Section 2 — `chain.json` schema (machine contract)

```json
{
  "topic": "auth-redesign",
  "slug": "2026-06-18-auth-redesign",
  "workspace": "sigma/specs/2026-06-18-auth-redesign",
  "generated_from": "weave",
  "stages": [
    {
      "name": "research", "artifact": "research.md", "exists": true,
      "bytes": 8123, "citations": 12,
      "headings": ["Executive summary", "Findings", "Gaps"]
    },
    { "name": "implement-task", "artifact": "impl/", "exists": true,
      "is_dir": true, "files": 3 },
    { "name": "verify", "artifact": "verify/", "exists": false,
      "is_dir": true, "files": 0 }
  ],
  "chain_complete": false,
  "missing": ["verify"]
}
```

Rules:
- Stage list comes from `pipeline.STAGES` (single source; weave_manifest imports
  it — no duplicate stage list to drift).
- **No timestamp generated in the pure function** (same discipline as
  `board.Event.ts`): caller passes it in or it is omitted. Keeps `build_manifest`
  deterministic/testable.
- `citations` = pure regex count of markdown links / `[n]` refs. `headings` =
  `^#+ ` lines. Both deterministic, no agent.
- `chain_complete` / `missing` = derived convenience for the verify consumer.
- File-artifact stages carry `bytes`/`citations`/`headings`; directory-artifact
  stages (`impl/`, `verify/`) carry `is_dir`/`files` instead.

## Section 3 — verify stage full-chain consumption (blast radius)

Only the **stage** `verify` path changes (in `cli/pipeline.py`). `loop.py`'s
per-task `VERIFY_PROMPT` (maker→checker) stays untouched — it grades one task's
diff; full-chain noise would hurt it, and `execute_cycle`'s maker≠checker
contract must stay 100% unchanged.

New behavior: when rendering the `verify` stage invocation, build a full-chain
context block from the manifest instead of just `spec.md`:

```
--- artifact chain (review against ALL of these) ---
[research]   research.md      (12 citations)  — <full text>
[propose]    proposals.md                     — <full text>
[blueprint]  architecture.md                  — <full text>
[spec]       spec.md                          — <full text>
[tasks]      tasks.md                         — <full text>
--- end chain ---
```

Guards:
1. **Fallback-safe ordering** — if `chain.json` is missing, verify falls back to
   the existing `spec.md`-only behavior (never hard-fails). Matches sigma's
   "broken gate defaults to WAKE" philosophy: a missing derived artifact never
   blocks the pipeline.
2. **Only existing file artifacts are inlined**; directory artifacts (`impl/`,
   `verify/`) are referenced via the manifest, not inlined.
3. **Scope: stage-verify only.** `loop.py` untouched. `PRIOR_ARTIFACT` stays as
   the fallback map.

Implementation seam: a new `chain_context(stage_name, workspace)` helper in
`pipeline.py` that returns the full-chain block for `verify` when a manifest
exists, else `None`; `render_invocation` prefers it over `prior_context` for the
verify stage, falling back to `prior_context` otherwise.

## Section 4 — HTML render spec (`chain.html`)

- **Single self-contained file.** Default CDN links (small, emailable); the agent
  prompt instructs a clean editorial layout (not a uniform card grid / stock
  gradient hero — honors the design-quality rules).
- **One section per present stage**, in pipeline order, cross-linked via a top
  nav / table of contents. Each section shows the stage name, the rendered
  artifact, and (for research) carried-through citations with fact/inference
  labels.
- **Provenance footer**: topic, slug, which stages present/missing, "derived from
  markdown — not source of truth".
- **a11y + motion**: include a `prefers-reduced-motion: reduce` block; animate
  only compositor-friendly props. (Reuses `sigma-present` conventions.)
- The agent's output is validated by `validate_chain_html` (well-formed; every
  present stage has a section). Validation problems are surfaced, not silently
  swallowed.

## Section 5 — CLI + plugin + testing

**CLI:** `sigma weave --topic <t>` (and `--dry-run` to print the invocation, like
every other stage). Wired into `cli/main.py` alongside `learn`/`board`. Writes
`chain.html` + `chain.json` into the spec workspace.

**Plugin:** new `commands/weave.md` slash-command template (CHAIN mode), mirroring
the stage 1:1 for the in-session path. Frontmatter: `command:`, `description:`,
`stage:`, `inputs:`/`outputs:`.

**Testing (≥80%, AAA):**
- `tests/test_weave_manifest.py` — pure: `build_manifest` over a fake workspace
  (file + dir artifacts, missing stages, citation/heading counts, chain_complete
  / missing); `validate_chain_html` (well-formed pass, missing-section fail,
  malformed fail). Deterministic (no timestamp in pure path).
- `tests/test_weave.py` — orchestrator with an injected fake `AgentRunner`:
  emits both files; agent failure still writes `chain.json` (manifest independent
  of agent); `--dry-run` prints, does not run.
- `tests/test_pipeline.py` (extend) — verify stage assembles full-chain context
  when manifest present; falls back to `spec.md` when manifest absent; `loop.py`
  verify path unchanged.

**Docs:** update `CLAUDE.md` (command list, layout, gotchas: derived-not-canonical,
fallback-safe verify, no-timestamp-in-pure-manifest) and `docs/PLAYGROUND.md`.

## YAGNI / non-goals

- No new runtime dependency (no markdown lib; agent renders HTML, pure code only
  counts/validates with stdlib `re`/`json`).
- No change to `loop.py` semantics.
- No auto-run of weave after every stage (explicit `sigma weave` + plugin only).
- Python 3.9-safe types throughout (`Optional[X]`/`List[X]`, no `X | None`).
