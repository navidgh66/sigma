---
command: /claude-md-create
description: Scaffold a best-practice-shaped CLAUDE.md (team-shared) or CLAUDE.local.md (personal, gitignored) — distinct from native /init, capped under 200 lines
stage: aux
inputs: ["target: repo|local (default repo)"]
outputs: ["CLAUDE.md or CLAUDE.local.md"]
---

# /claude-md-create

Scaffold a best-practice-shaped starter — distinct from Claude Code's native
`/init`, which scans the repo with no length/structure discipline and often
produces bloated output (research finding: repo-overview/architecture content
is the most commonly auto-generated content yet measurably doesn't improve task
success on its own).

## Target
- `repo` (default) → **CLAUDE.md** — team-shared, committed to git.
- `local` → **CLAUDE.local.md** — personal to this developer, gitignored. Check
  if CLAUDE.md already exists first; don't duplicate what's already there.

## Refuse to overwrite
If the target file already exists, STOP and say so — do not clobber it. The user
can ask again explicitly with intent to overwrite.

## Write the file
Target UNDER 200 lines. For every line: would removing it cause a mistake? If
not, don't write it.

Structure:
```
# <project name>

## What
<tech stack, project structure — pointers not prose, 2-3 lines>

## Why
<purpose of this project / this part of it — 1-2 lines>

## How
<exact commands Claude can't guess, non-default conventions, gotchas>
```

**Include**: bash commands Claude can't guess, code style that differs from
defaults, testing instructions, repo etiquette (branch naming, PR conventions),
project-specific architectural decisions, dev-environment quirks, real gotchas.

**Exclude**: anything discoverable by reading the code, standard language
conventions, detailed API docs (link instead), long tutorials, file-by-file
descriptions, self-evident practices.

Use file:line pointers, never pasted code snippets. Write in imperative voice.
Walk the actual codebase (package manifests, Makefiles, existing conventions,
test runner) and fill the structure with REAL facts — never a placeholder.

For `local` target: capture only things specific to THIS developer's workflow on
this machine (personal aliases, local env quirks) — never duplicate what belongs
in the shared CLAUDE.md.

## Next
→ `/claude-md-check` to verify the result against the same research rubric.
