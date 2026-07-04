---
name: sigma-docs
description: >
  Generate EXTERNAL-facing project documentation from the codebase itself —
  README, API/reference docs (from code signatures + docstrings), CHANGELOG /
  release notes (from git log), and an "about this project" presentation.
  Grounds in ARCHITECTURE.md when present; delegates HTML/theming for
  presentations to sigma-present. Use when the user wants docs for an AUDIENCE
  (users, contributors, release readers) — not internal onboarding. Triggers:
  "write a README", "generate API docs", "draft release notes", "make a
  project overview deck", "document this for users".
origin: sigma
---

# sigma-docs

Generate **external-facing** project documentation straight from the
codebase: README, API reference, CHANGELOG/release notes, and a project
overview presentation. The audience is someone outside the pipeline — a user,
a contributor, a release reader — not another sigma stage.

## When to use

This is the third leg of a trio; know which one you are:

- **`codebase-onboarding`** — generates an INTERNAL onboarding guide + starter
  `CLAUDE.md` for a developer joining the project. Audience: the next
  contributor working ON the code.
- **`sigma-present`** — transforms an EXISTING sigma pipeline artifact
  (`research.md`, `spec.md`, `tasks.md`, `board.md`, verify output) into HTML.
  It never generates fresh documentation content — it only re-renders what
  another stage already wrote.
- **`sigma-docs` (this skill)** — generates FRESH documentation FROM the
  codebase itself, for an audience OUTSIDE the project: users reading a
  README, contributors reading API docs, release readers reading a
  CHANGELOG. It is not onboarding, and it is not a re-render of a prior
  artifact.

Use `sigma-docs` when the user wants a README, API/reference docs, a
CHANGELOG or release notes, or an "about this project" deck/overview meant to
be shared outside the pipeline.

## Mode decision table

| Trigger | Mode | Output lands |
|---------|------|---------------|
| "README", "readme", "project intro" | **README** | repo-root `README.md` |
| "API docs", "reference", "document the functions/classes" | **API-REFERENCE** | `docs/` (e.g. `docs/reference.md`) |
| "changelog", "release notes", "what changed", "since vX" | **CHANGELOG** | repo-root `CHANGELOG.md` |
| "overview deck", "about this project", "pitch", "present the project" | **PRESENTATION** | markdown draft → hand off to sigma-present → `export.html` |

Default: an ambiguous "document this" → **README**.

## Composition contract

- **With `sigma learn`** — if `ARCHITECTURE.md` exists at the project root,
  read it first and ground every architecture claim in it, citing it ("per
  ARCHITECTURE.md") rather than re-deriving the architecture from scratch. If
  it's absent, note that and suggest running `/learn` first, but proceed
  anyway on direct code reading — this must NOT hard-require
  `ARCHITECTURE.md` to exist (fail-safe, same posture as the rest of sigma's
  optional-artifact composition).
- **With `codebase-onboarding`** — that skill is for INTERNAL dev onboarding;
  `sigma-docs` is for an EXTERNAL audience. If an onboarding guide or starter
  `CLAUDE.md` already exists, `sigma-docs` may reuse its detected stack and
  conventions as evidence instead of re-detecting them from scratch, but it
  must not duplicate that skill's purpose (no onboarding guide, no starter
  `CLAUDE.md` out of this skill).
- **With `sigma-present` (PRESENTATION mode only)** — `sigma-docs` produces a
  markdown draft only: an H1 title and H2 sections (what it is / why /
  architecture-at-a-glance / usage / roadmap). It NEVER emits HTML, CSS, or
  themes itself. It then hands the draft to `sigma-present`, naming the exact
  artifacts `sigma-present`'s `INGEST.md` expects — H1 → hero/title, H2 →
  sections, citations → Sources. **sigma-docs must never build a second HTML
  pipeline.**

## Per-mode workflow

- **README** — gather evidence: package manifest, entry points,
  `ARCHITECTURE.md` if present, and real commands from `Makefile` /
  `scripts/` / `pyproject.toml` / `package.json`. Write sections (one-line
  what/why, install, quick start, key features) with each claim grounded in a
  real command or module. PRESERVE EXISTING CONTENT: if `README.md` already
  exists, read it first and enhance/merge rather than overwrite wholesale —
  the same "enhance, don't replace" law `codebase-onboarding` applies to
  `CLAUDE.md`. Call out clearly what was added/changed vs what was preserved.
- **API-REFERENCE** — enumerate public signatures and docstrings
  language-agnostically (via Grep/Read over exported functions/classes/
  symbols); render one reference section per module. Do NOT invent params or
  behavior — an absent docstring means "undocumented", not a guess.
- **CHANGELOG** — run `git log` directly (Bash is available — no graphify or
  extra tooling needed), group commits by conventional-commit prefix per the
  mapping in `CHANGELOG-CONVENTIONS.md`, and produce Keep-a-Changelog-style
  sections. Support "since vX" via `git log vX..HEAD`. PRESERVE EXISTING
  CONTENT: if `CHANGELOG.md` already exists, APPEND a new dated section for
  the new range — never regenerate or overwrite prior history.
- **PRESENTATION** — build the markdown draft per the composition contract
  above, then delegate to `sigma-present` for HTML/theming.

## Anti-slop

- Don't invent features, flags, or config that aren't actually in the code.
- Don't pad with emoji headers or marketing filler ("blazing fast",
  "seamless", "revolutionary").
- Every claim must trace to a real file, command, or commit — if you can't
  point to the evidence, don't write the claim.
- Don't copy the README verbatim into the API docs — they serve different
  readers.
- Don't restate obvious directory names ("`src/` — source code").
- Write "undocumented" rather than fabricate what a missing docstring means.
- A CHANGELOG entry must map to a real commit hash/message — never invent one.
- Keep READMEs scannable — don't pad length for its own sake.

## Files in this skill

- `SKILL.md` — this file.
- `CHANGELOG-CONVENTIONS.md` — conventional-commit → Keep-a-Changelog section
  mapping, git recipes, and the changelog format skeleton.

## Common mistakes

- Overwriting a hand-maintained README instead of enhancing it.
- Building HTML/CSS for PRESENTATION mode instead of delegating to
  `sigma-present`.
- Inventing changelog entries not backed by a real commit.
- Confusing this skill's external audience with `codebase-onboarding`'s
  internal audience — or treating it as another `sigma-present` re-render.
