# Design: `--team` real git-worktree isolation

**Date:** 2026-07-04
**Status:** approved (brainstorm → plan), ready to implement
**Branch:** `feat/team-worktree-isolation`

---

## Problem

`sigma loop --execute --team` runs N independent tasks CONCURRENTLY via a
`ThreadPoolExecutor` (`run_loop(team=True)` in `cli/loop.py`), but every task's
implementer/verifier agent runs with the SAME `cwd` — one shared working tree.
`IMPLEMENT_PROMPT` doesn't sandbox the agent to any subdirectory; the agent is
free to edit any file in the checked-out repo. Two concurrent tasks touching
overlapping files is a real collision risk (interleaved edits, one task's
uncommitted diff affecting another's verify read) — not a designed guarantee,
just accidental safety when task domains happen not to overlap.

Separately, `cli/config.py`'s `LoopConfig.worktrees: bool = True` is declared and
serialized into `sigma.config.yml`, but read nowhere in the codebase — a dead
flag implying a feature that doesn't exist.

## Scope

**`--team` mode only.** Sequential mode (default, one task at a time) has no
concurrency risk — one agent, one tree, no collision possible. Worktree
creation/teardown overhead buys nothing there, so sequential mode is untouched.

## Design

### New module: `cli/worktree.py`

Pure logic + injectable subprocess, mirroring `cli/runner.py`'s split (the
`AgentRunner` pattern: a `runner: Callable = subprocess.run` field so tests never
spawn real git).

```python
def worktree_path(project_root: Path, name: str) -> Path:
    """`.worktrees/<name>` under the project root."""

def ensure_worktrees_ignored(project_root: Path) -> None:
    """Add `.worktrees/` to .gitignore + commit if not already ignored.
    Mirrors the vendored using-git-worktrees skill's own safety check."""

def create_worktree(project_root: Path, name: str, base_branch: str,
                     runner: Callable = subprocess.run) -> "WorktreeResult":
    """`git worktree add .worktrees/<name> -b <name> <base_branch>`."""

@dataclass
class MergeResult:
    ok: bool
    conflict: bool = False
    error: Optional[str] = None

def merge_worktree(project_root: Path, name: str, base_branch: str,
                    runner: Callable = subprocess.run) -> MergeResult:
    """`git merge --no-ff <name>` onto base_branch. Never auto-resolves a
    conflict — returns conflict=True and leaves the tree in the pre-merge
    state (caller decides what to do; this function does not abort/retry)."""

def remove_worktree(project_root: Path, name: str, force: bool = False,
                     runner: Callable = subprocess.run) -> None:
    """`git worktree remove` + `git branch -D <name>`."""
```

### `cli/loop.py` changes

**`execute_cycle`** gains one new optional param:

```python
def execute_cycle(
    plan, workspace, skills_dir, implementer, verifier,
    ...,
    agent_cwd: Optional[Path] = None,
) -> CycleOutcome:
```

`agent_cwd` is where the implementer/verifier/advisor/simplifier subprocess
actually runs (`cwd=` on every `.run()` call). `workspace` stays where
artifacts/logs/ratchets are written (`impl/*.md`, `verify/*.md`, `loop-log.md`,
`advisor/*.md` — unchanged). When `agent_cwd` is `None` (every existing caller,
every existing test), it falls back to `workspace` — byte-identical to today.
`--team` is the first and only caller that passes `agent_cwd` explicitly.

**`CycleOutcome`** gains one new field: `merge_conflict: Optional[Path] = None`
— set to the worktree path when a PASSing cycle's merge conflicts. Same shape
as the existing `contradiction` field (surfaced, never auto-resolved).

**`run_loop(..., team=True)`** restructures the team branch:

1. Before fan-out (sequential, same place the recall cache is pre-built today —
   no races): if `cfg.loop.worktrees` is true (passed in as a new `worktrees:
   bool = True` param), create one worktree per batch task via
   `create_worktree(project_root, plan.worktree_name, base_branch=<current
   branch>)`. If `worktrees=False`, skip entirely — every task gets
   `agent_cwd=None`, reproducing today's shared-workspace `--team` behavior
   byte-for-byte (the escape hatch for no-git/sandboxed environments).
2. `run_one(task)` passes `agent_cwd=worktree_path` (or `None` if worktrees are
   off) into `execute_cycle`.
3. After each outcome:
   - **PASS** → `merge_worktree`. No conflict → `remove_worktree`. Conflict →
     do NOT remove; set `outcome.merge_conflict = worktree_path`; leave the
     worktree+branch on disk for manual resolution.
   - **FAIL / advisor-exhausted** → `remove_worktree` directly. The ratcheted
     skill lesson + the artifact markdown copies are the record that matters;
     the failed worktree itself isn't kept.

### `cli/config.py`

`LoopConfig.worktrees: bool = True` — the flag is no longer dead. Read by
`cmd_loop`/`run_loop` to gate the isolation logic above. Default `True` (real
isolation is the new `--team` default); a project sets `worktrees: false` in
`sigma.config.yml` to opt out (no git available, sandboxed CI, etc).

### `cmd_loop` output

New line per outcome when `o.merge_conflict` is set, matching the existing
`⚠ contradiction flagged` line's shape:

```
⚠ merge conflict — branch left at .worktrees/sigma-loop-t2 for manual resolution
```

## What does NOT change

- Sequential mode: `agent_cwd` always `None`, zero worktree calls, zero behavior
  change.
- Artifact paths (`impl/`, `verify/`, `advisor/`, `regressions/`, `loop-log.md`,
  `trajectory.jsonl`, `costs.jsonl`) — all still land in the one shared
  `sigma/specs/{date}-{slug}/` workspace regardless of `--team`/worktrees. Only
  the AGENT's `cwd` moves; the bookkeeping location doesn't.
- The advisor axis, simplify axis, TDD axis, logic axis — all pass through
  `agent_cwd` unchanged; none of their internal logic needs to know about
  worktrees.
- `skills/vendor/superpowers/using-git-worktrees` stays unwired from
  `cli/skill_map.py`'s `STAGE_SKILLS` — this feature gives sigma REAL worktree
  mechanics via `cli/worktree.py`, so injecting the vendored skill's prose into
  an agent prompt (which tells the AGENT to self-manage isolation) is now
  actively the wrong layer; sigma's own loop code manages isolation, the agent
  never needs to know a worktree exists.

## Testing

- `tests/test_worktree.py` — pure module tests using a REAL temp git repo (not
  mocks) per test, matching the rigor already established for the advisor axis:
  create → verify `.worktrees/<name>` exists and is on its own branch; merge
  clean → verify base branch has the commit; merge conflicting → verify
  `MergeResult.conflict is True` and nothing was force-resolved; remove →
  verify the worktree dir and branch are both gone.
- `tests/test_loop_exec.py` — `run_loop`-level tests for the `--team` +
  worktree path: PASS → merge → remove (real temp repo); FAIL → remove, no
  merge attempt; a genuine merge conflict → `outcome.merge_conflict` set,
  worktree left on disk; `worktrees=False` → byte-identical to today's shared-
  workspace `--team` (regression guard, same style as the earlier
  `test_no_route_reproduces_unrouted` test).
- `tests/test_config.py` (or wherever `LoopConfig` is tested) — round-trip
  `worktrees: false` through `sigma.config.yml`.
- Live functional test after implementation (not just pytest): run
  `sigma loop --topic <t> --execute --team` against a real scratch git repo
  with a fake `claude` shim (same technique used for the advisor axis
  verification), confirm real `git worktree list` shows the branches, confirm
  a real merge lands the commit, confirm cleanup removes them.
