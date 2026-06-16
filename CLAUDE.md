# CLAUDE.md — sigma

Guide for AI assistants working in the sigma repo.

## What this is

`sigma` is a personal, portable AI workflow toolkit for data science & AI
engineering. A Python CLI + markdown templates that wrap Claude Code with a
research-first, spec-driven, loop-engineered pipeline. Core and execution are
complete: all 8 stages run through one injectable agent runner; the loop runs
real maker→checker cycles. 65 pytest tests, ruff clean.

## Commands

```bash
python3 -m pytest tests/ -q          # run all 65 tests (must stay green)
python3 -m ruff check cli/ tests/    # lint (py39 target)
python3 -m ruff check --fix cli/ tests/

python3 -m cli.main --help           # CLI help
sigma init --domains nlp,rl          # scaffold sigma.config.yml for a project
sigma research "topic"               # multi-model research → research.md
sigma spec --topic <t>               # run one pipeline stage (writes artifact)
sigma spec --topic <t> --dry-run     # print the invocation, don't run claude
sigma loop --topic <t>               # plan cycles (safe default)
sigma loop --topic <t> --execute     # run maker→checker cycles
```

## Pipeline

`research → propose → blueprint → spec → tasks → implement-task → verify → loop`

Each stage reads the prior stage's artifact as context. Artifacts live under
`sigma/specs/{YYYY-MM-DD}-{slug}/`.

## Layout

```
cli/__init__.py     __version__
cli/main.py         argparse CLI: init / research / <stages> / loop / launch
cli/config.py       sigma.config.yml load/write/validate + local override merge
cli/paths.py        DOMAINS (9), project root, spec workspace, slugify
cli/models.py       research model adapters (claude/gemini/gpt), graceful skip
cli/research.py     parallel fan-out + cited aggregation → research.md
cli/runner.py       AgentRunner — the single execution chokepoint (injectable)
cli/pipeline.py     execute_stage: run stage, chain prior artifact, persist
cli/loop.py         parse tasks, execute_cycle (maker→checker), ratchet, run_loop
cli/worktree.py     git worktree create/remove for parallel-safe loop isolation
commands/           8 slash-command templates (one per stage), YAML frontmatter
context-engines/<d>/  9 domains, implementers/ + verifiers/ (NLP & RL deep)
subagents/researchers/  claude / gemini / gpt research subagents
skills/             ratcheted lessons (SKILL.md), written on loop failures
installer/setup.sh  one-line global install
docs/               design doc + roadmap
```

## Principles

- **Loop engineering** — design loops, stay the engineer. Failures ratchet into `skills/`.
- **Maker ≠ checker** — implementer and verifier are always distinct agents.
- **Lean context** — load only the domain a task needs.
- **Multi-model research** — Claude + Gemini + GPT in parallel, aggregated, cited.
- **YAGNI** — no dashboard/telemetry/TS port until the single-user core proves out.

## Conventions

- **Python 3.9** target. Keep type hints 3.9-safe: use `Optional[X]` / `List[X]`
  from `typing`, NOT `X | None` (ruff `UP` rule is intentionally disabled).
- Standard library first; keep the CLI dependency-light (only `pyyaml` runtime).
- Markdown templates use YAML frontmatter.
- Every research claim is cited; separate fact from inference.

## Gotchas

- `execute_cycle` raises `ValueError` if the same runner instance is passed as
  both maker and checker — separation is enforced, not advisory.
- Verdict parsing is skeptical: a checker reply missing `VERDICT: PASS` is
  treated as FAIL.
- `sigma loop` plans by default; it only executes cycles with `--execute`.
- Pure logic (config, paths, parsing, cycle planning) is separated from
  subprocess execution so everything is testable with injected fakes.
- All agent/model invocation passes the prompt via argv (never the shell) — no
  injection risk; preserve that when adding adapters.
