---
command: /scout
description: Discover skills relevant to sigma's domains on skillsmp.com, surface a relevance-ranked table, install only what a human approves
stage: aux
inputs: ["sigma.config.yml domains", "skills/ + skills/vendor/ (dedup)", "SKILLSMP_API_KEY (optional, ~/.sigma/.env)"]
outputs: ["newly cloned skills under .claude/skills/ (or skills/vendor/ with --vendor)"]
---

# /scout

Keep sigma's skill bundle fresh against [skillsmp.com](https://skillsmp.com) (a very
large community catalog). Scout queries per sigma domain, scores relevance, drops
anything already bundled, and **surfaces a ranked table — it never auto-installs.**

## How it runs
1. Read the project's domains from `sigma.config.yml` (fallback: all 9).
2. For each domain, query `GET /api/v1/skills/search` with the domain's terms +
   category (stdlib `urllib`, no new dependency). An optional `SKILLSMP_API_KEY`
   in `~/.sigma/.env` raises the daily rate limit; anonymous works at a lower rate.
3. Aggregate, dedup (across queries AND against `skills/` + `skills/vendor/`), and
   rank by relevance (domain-keyword overlap > popularity — a popular-but-irrelevant
   skill never outranks a relevant one).

## The law: surface, never auto-resolve
- Every candidate is shown with its name, stars, repo, and description.
- Installation is **per-skill confirmed by a human**, who checks the license first.
- This mirrors contradiction flagging: scout proposes, a person decides.

## Targets
- default → the project's `.claude/skills/` (use it in this repo now).
- `--vendor` → sigma's own `skills/vendor/` (maintainer mode); review + commit to
  grow the shipped bundle.

## Flags
- `--category <slug>` — restrict to one skillsmp category.
- `--recent` — sort by newly-added instead of stars (catch fresh trends).
- `--dry-run` — show the ranked candidates, install nothing.

## Fail-safe
skillsmp unreachable / rate-limited / bad payload → an empty result + a banner,
never a crash. A partial sweep still ranks what came back.

## Next
→ review a candidate's repo + license · install the keepers · `--vendor` then commit
to update the sigma bundle.
