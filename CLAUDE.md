# CLAUDE.md — sigma

Guide for AI assistants working in the sigma repo.

## What this is

`sigma` is a personal, portable AI workflow toolkit for data science & AI
engineering. Python CLI + markdown templates that wrap Claude Code with a
research-first, spec-driven, loop-engineered pipeline.

## Pipeline

`/research → /propose → /blueprint → /spec → /tasks → /implement-task → /verify → /loop`

Artifacts live under `sigma/specs/{YYYY-MM-DD}-{slug}/`.

## Layout

```
cli/main.py            CLI entry (argparse skeleton)
commands/              slash-command templates (one per pipeline stage)
context-engines/<d>/   per-domain knowledge (implementers/ + verifiers/)
subagents/researchers/ claude / gemini / gpt research subagents
skills/                ratcheted lessons (SKILL.md)
installer/setup.sh     one-line global install
docs/                  design doc + roadmap
```

## Principles

- **Loop engineering** — design loops, stay the engineer. Failures ratchet into `skills/`.
- **Maker ≠ checker** — implementer and verifier are always separate agents.
- **Lean context** — load only the domain a task needs.
- **Multi-model research** — Claude + Gemini + GPT in parallel, aggregated, cited.
- **YAGNI** — no dashboard/telemetry/TS port until the single-user core proves out.

## Conventions

- Python 3.10+, standard library first; keep the CLI dependency-light.
- Markdown templates use YAML frontmatter.
- Every research claim is cited; separate fact from inference.
