---
name: sigma-claude-md
description: >
  Check or scaffold CLAUDE.md / CLAUDE.local.md against best-practice research
  (official Anthropic guidance + community consensus + real-world examples).
  Use when running /claude-md-check or /claude-md-create, when a human asks to
  "check", "audit", "improve", or "review" a CLAUDE.md file, or when scaffolding
  a new one and native /init would produce unbounded, undisciplined output.
  Carries the length/structure/specificity rubric both commands share.
origin: sigma
---

# sigma-claude-md

The **CLAUDE.md rubric** — what a best-practice check or scaffold enforces,
distilled from a deep-research pass (2026-07-10) across official Anthropic docs,
community practitioner consensus, and 5 real-world repos (cloudflare/workers-sdk,
vercel/ai, supabase, humanlayer, langchain).

**The one law underneath every check**: *for each line, would removing it cause
Claude to make a mistake? If not, it doesn't belong.* Bloat is the dominant
documented failure mode — a long CLAUDE.md doesn't fail loudly, Claude silently
discounts parts of it (Claude Code injects a system-reminder around CLAUDE.md
content saying "you should not respond to this context unless it is highly
relevant" — that's the mechanism, not just an anecdote).

## Length thresholds
- Official target: **under 200 lines**. Community consensus converges on the
  same number, with a **~300-line outer ceiling** before adherence measurably
  degrades. >300 = HIGH, 200-300 = MEDIUM.
- Nested/per-package CLAUDE.md files are a NATIVE Claude Code mechanism for
  monorepos, not a workaround — a subdirectory's CLAUDE.md loads lazily, only
  when Claude reads a file there. Prefer nesting over one giant root file.

## Include / exclude (official table, verbatim)
| ✅ Include | ❌ Exclude |
|---|---|
| Bash commands Claude can't guess | Anything Claude can figure out by reading code |
| Code style rules that differ from defaults | Standard language conventions Claude already knows |
| Testing instructions and preferred test runners | Detailed API documentation (link to docs instead) |
| Repository etiquette (branch naming, PR conventions) | Information that changes frequently |
| Architectural decisions specific to your project | Long explanations or tutorials |
| Developer environment quirks (required env vars) | File-by-file descriptions of the codebase |
| Common gotchas or non-obvious behaviors | Self-evident practices like "write clean code" |

## Formatting
- **File:line pointers, never pasted code** — a snippet goes stale, a pointer
  doesn't. Any fenced code block over ~15 lines is a smell.
- **Imperative voice** — "use X" not "we generally prefer X".
- **WHAT / WHY / HOW structure** — tech stack & layout (WHAT), purpose (WHY),
  workflow & verification steps (HOW). Peer-reviewed evidence (arXiv:2602.11988)
  found repo-overview/architecture content specifically does NOT improve task
  success despite being the most common auto-generated content — don't over-
  invest in WHAT at the expense of HOW.
- **`@path` imports** are organizational only — they do NOT reduce context (an
  imported file still loads at launch). A broken import is a real defect
  (resolves relative to the importing file, not cwd, per official docs).

## Register
CLAUDE.md is written FOR an agent, not for a human onboarding to the repo.
README voice (narrative history, marketing framing, "in conclusion") is a
register mismatch even when the facts are true.

## Maintenance
Treat it as a living document: update the moment Claude repeats a mistake twice,
prune the moment a rule becomes redundant. Commit to git, review changes like
code. `CLAUDE.local.md` (gitignored) is for personal-only preferences — never
duplicate what belongs in the shared file.

## Composes with
- `/claude-md-check` — runs deterministic checks (length, pasted code, broken
  imports, stale test/line counts, placeholders) + this qualitative rubric
  against CLAUDE.md (required) and CLAUDE.local.md (optional, skipped if absent).
- `/claude-md-create` — scaffolds a WHAT/WHY/HOW starter capped under 200 lines,
  distinct from native `/init` (no length/structure discipline there). Refuses
  to overwrite an existing file.
- `sigma setup-repo` — offers `/claude-md-create` when neither file exists yet,
  or surfaces a `/claude-md-check` finding when one already does (same
  exists→check / missing→offer-create shape as the learn-artifacts step).
