# Design: Closed Learning Loop

**Date:** 2026-06-19
**Status:** Approved (all sections)
**Topic:** Make ratcheted lessons *usable* on future runs (recall), and let a human
ratchet a lesson from the current session outside the loop.

## Motivation

Today the loop ratchets a lesson into `skills/<slug>/SKILL.md` on failure (tagged
`domain:`), and `skills_index.find_contradictions` flags conflicts — but **nothing
reads lessons back into a future run**. Learning is recorded, not applied. Also,
ratcheting only happens inside `sigma loop`; in-session work (`/spec`,
`/implement-task`) can hit a mistake the human wants captured, with no path to do
so.

Two features close this:

- **A — Recall:** select past lessons by domain and inject them into future runs
  (loop cycles + in-session via a skill).
- **B — Manual learn:** a plugin command `/sigma-learn-lesson` where the agent
  extracts a mistake → lesson → domain from the current session and ratchets it
  through the same store/format/contradiction path as loop failures.

## Invariants preserved

- One store, one format, one contradiction check, one recall path for both
  loop-born and manually-captured lessons.
- Maker ≠ checker enforcement unchanged.
- Fail-safe: empty skills/ or no domain match → behavior identical to today
  (no recall block, prompts byte-identical).
- Python 3.9-safe types. No new runtime dependency. Domain-match recall only —
  no embeddings/semantic search (YAGNI).

## Section 1 — Architecture (the closed loop)

New pure module **`cli/skills_recall.py`** (mirrors `cli/skills_index.py`):

- `recall_lessons(skills_dir, domain) -> List[Lesson]` — scan
  `skills/**/SKILL.md`, return those whose frontmatter `domain:` matches. Skills
  without a `domain:` (vendor, sigma-present, sigma-domains) are naturally
  excluded. Reuses `skills_index.parse_skill_meta`.
- `render_recall_block(recall) -> str` — compact "Past lessons (avoid
  repeating)" block from a `Recall` (the `limit`/cap lives in `recall_lessons`,
  which returns a `Recall{lessons, truncated}`): each lesson's title + the
  `**Lesson (ratcheted):**` line + the how-to-apply line. Deterministic; notes
  truncation when lessons were dropped. Empty → "".

Data flow (now a closed loop):

```
failure → ratchet_to_skills (exists) → skills/<slug>/SKILL.md
        → recall_lessons (new) → render_recall_block → injected into next run
```

Two injection points:
1. **Loop** — domain recall block prepended to a cycle's implement + verify
   prompts.
2. **In-session** — new skill `skills/sigma-lessons/` surfaces recalled lessons
   by domain (sibling to `sigma-domains`).

## Section 2 — Loop recall injection

- `execute_cycle` gains optional `recall: str = ""`. When set, prepend to
  `IMPLEMENT_PROMPT` and `VERIFY_PROMPT` (maker avoids past mistakes; checker
  checks against them). NOT the logic prompt (it grades reasoning, not domain
  patterns).
- `run_loop` builds the recall block **once per domain** (cache keyed by domain
  across cycles — avoids re-scanning skills/ every task) via
  `recall_lessons` + `render_recall_block`, and passes it into each
  `execute_cycle`.
- Self-reference is safe: recall is built when each cycle starts; the task that
  failed has already ended, so its fresh lesson can legitimately surface for the
  NEXT task in the same domain. No infinite loop.
- Fail-safe: no lessons / no domain match → `recall=""` → prompts unchanged.
- Maker ≠ checker untouched (recall is added context only).

## Section 3 — Manual learn (`/sigma-learn-lesson`)

New plugin command **`commands/sigma-learn-lesson.md`** (in-session):

- Trigger: human says "learn from this mistake" / `/sigma-learn-lesson`.
- The agent reviews the current session and extracts: the mistake, the lesson to
  apply next time, and the domain (one of the 9, or `general`).
- Writes via the SAME `ratchet_to_skills` contract → `skills/<slug>/SKILL.md`
  with a `domain:` tag and identical contradiction flagging.
- The lesson title uses a `session lesson:` prefix (vs `verify failed:` /
  `implement failed:`). Add `"session lesson:"` to `skills_index._NOISE_PREFIXES`
  so manual + loop lessons on the same topic still collide for contradiction
  detection AND recall keys match.
- Output: confirm the written path + any ⚠ contradiction.

No new Python is strictly required for the write (ratchet_to_skills exists);
the command instructs the agent to follow the documented format. The only Python
change is the `_NOISE_PREFIXES` addition.

## Section 4 — Testing + docs

Tests:
- `tests/test_skills_recall.py` (pure): `recall_lessons` matches by domain,
  excludes no-domain/vendor skills, excludes other domains; `render_recall_block`
  includes lesson text, caps at N, empty→"".
- `tests/test_loop_exec.py` (extend): `execute_cycle(recall=...)` prepends to
  implement + verify prompts (assert via fake runner capturing the prompt), NOT
  to logic; empty recall → prompts identical to today (regression guard).
- `tests/test_skills_index.py` (extend): `"session lesson:"` prefix stripped by
  `topic_key` → manual + loop lesson on same topic collide.

Docs:
- CLAUDE.md — new modules in Layout; loop gotcha notes the loop is now *closed*
  (lessons recalled, not just recorded); `/sigma-learn-lesson` + `sigma-lessons`
  skill in the plugin list.
- PLAYGROUND.md — short section on recall + manual learn.

Sequencing (3 commits):
1. `cli/skills_recall.py` (pure) + tests.
2. Loop wiring (`execute_cycle`/`run_loop` recall) + `skills/sigma-lessons` skill
   + `_NOISE_PREFIXES` addition + tests.
3. `/sigma-learn-lesson` command + docs.

## YAGNI / non-goals

- No embeddings / semantic recall — domain-match only.
- No auto-editing existing lessons — contradictions stay human-decided.
- No recall in pure pipeline stages beyond the `sigma-lessons` skill.
