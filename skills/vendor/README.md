# Vendored skills

Bundled copies of third-party Claude Code skills so sigma is **self-contained** —
Hermes can inject them per stage, and each works standalone in Claude Code even
when the upstream plugins are not installed.

These are unmodified copies. Do not edit them here; update upstream and re-vendor.

## Provenance

| Skill | Source plugin | Version | License |
|-------|---------------|---------|---------|
| `superpowers/brainstorming` | claude-plugins-official / superpowers | 6.0.0 | upstream |
| `superpowers/writing-plans` | claude-plugins-official / superpowers | 6.0.0 | upstream |
| `superpowers/test-driven-development` | claude-plugins-official / superpowers | 6.0.0 | upstream |
| `superpowers/systematic-debugging` | claude-plugins-official / superpowers | 6.0.0 | upstream |
| `superpowers/verification-before-completion` | claude-plugins-official / superpowers | 6.0.0 | upstream |
| `caveman` | caveman marketplace | (vendored) | upstream |

Scripts and internal test fixtures from the upstream skills are intentionally
omitted; only the skill instructions and reference docs are vendored.

## How sigma uses these

`cli/skill_map.py` maps each pipeline stage to one or more vendored skills and
injects the skill body into the stage prompt. See `STAGE_SKILLS` there.

## Re-vendoring

To refresh from upstream, copy the markdown (not `scripts/`) from the installed
plugin skill dirs back into the matching folder here, then bump the version above.
