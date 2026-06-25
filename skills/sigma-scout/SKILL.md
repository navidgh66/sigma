---
name: sigma-scout
description: >
  Discover skills relevant to sigma's domains on skillsmp.com and keep the bundle
  fresh, without ever auto-installing. Use to find trending or new community skills
  for classic-ml / deep-learning / nlp / rl / data / agents / mlops / llm work,
  vet them, and pull the keepers in. Triggers: "find new skills", "what skills
  should sigma add", "scout skillsmp", "keep the bundle current", "any trending
  skills for <domain>", or a periodic bundle refresh.
origin: sigma
---

# sigma-scout

Keep sigma's skill/plugin bundle current against [skillsmp.com](https://skillsmp.com)
— a very large community catalog. The pure scoring/dedup/rank logic lives in
`cli/scout.py`; the network + install in `cli/scout_run.py`. This skill is the
curation rubric.

## The one hard rule: surface, never auto-install
Scout proposes a relevance-ranked table; a **human picks** and checks each skill's
license before install. This is the same law as contradiction flagging and the
review gate — the tool never silently mutates the bundle.

## Relevance bar (how candidates are judged)
1. **Relevance FLOOR — pure noise is dropped, not just out-ranked.** A hit needs at
   least one *whole-token* domain-keyword match to clear the floor; a popular-but-
   off-topic skill scoring only on the capped star bump never surfaces. (Scout used
   to surface whatever it found up to the cap — the floor closes that hole.)
2. **Token match, not substring.** Domain terms match on whole tokens, so `rag`
   credits "rag retrieval" but NOT "sto**rag**e"/"f**rag**ment", and `data` does not
   match "meta**data**". Substring overlap inflated relevance on noise.
3. **Domain fit dominates; quality second.** Keyword overlap drives the score; stars +
   recency only break ties (the star bump is capped so popularity can't outrank fit).
4. **Per-author diversity cap.** At most a few hits from one author surface, so a
   prolific publisher can't flood the table and crowd out alternatives.
5. **Already-bundled → dropped.** Anything whose repo or name already lives under
   `skills/` or `skills/vendor/` is deduped out — scout only ever surfaces *new* skills.

## Before adding a skill (vetting checklist)
- **License** — confirm it permits redistribution if going into the sigma bundle
  (`--vendor`). Surface it; a human decides.
- **Maintenance** — recent commits, non-trivial stars, a real README.
- **Overlap** — does it duplicate an existing sigma skill or context-engine? If so,
  prefer improving ours over vendoring a near-duplicate (YAGNI).
- **Scope** — does it serve a domain sigma actually covers? Don't widen scope just
  because a skill is popular.

## Targets
- **project** (default) — clone into `.claude/skills/` to use in the current repo.
- **`--vendor`** (maintainer) — clone into sigma's `skills/vendor/`; then review +
  commit to grow the shipped bundle. Treat `skills/vendor/` as unmodified upstream
  copies (the existing vendor law) — don't hand-edit in place; re-vendor to update.

## Rate + keys
Anonymous skillsmp access is rate-limited (≈50/day). A free `SKILLSMP_API_KEY` in
`~/.sigma/.env` (never the committed config) raises it (~500/day). Optional.

## Fail-safe
API down / rate-limited / malformed payload → empty result + a banner, never a
crash. A partial sweep still ranks what returned.

## Compose, don't duplicate
Scout *grows* the bundle; `sigma-prune` *trims* what's unused; `sigma-cost` sizes
the token cost of carrying them. Three distinct layers of bundle hygiene.
