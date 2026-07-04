# --team Real Git-Worktree Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `sigma loop --execute --team` real per-task git-worktree isolation instead of running every concurrent task's agents in one shared working tree.

**Architecture:** New pure-logic module `cli/worktree.py` (injectable `subprocess.run`, mirrors `cli/runner.py`'s `AgentRunner` split) provides create/merge/remove primitives. `cli/loop.py`'s `execute_cycle` gains an optional `agent_cwd` param (defaults to `workspace`, so every existing caller is byte-identical); `run_loop`'s `team=True` branch creates one worktree per batch task before fan-out, merges on PASS (surfacing — never auto-resolving — conflicts), and removes on FAIL or after a clean merge. `cli/config.py`'s previously-dead `LoopConfig.worktrees` flag becomes the real on/off gate, threaded through `cmd_loop` → `run_loop`.

**Tech Stack:** Python 3.9, pytest, real temporary git repos for `cli/worktree.py` and the new `run_loop` team+worktree tests (no mocking of `git` itself — only `AgentRunner`/agent subprocesses are scripted, exactly as the rest of the suite already does).

## Global Constraints

- Python 3.9 type hints only: `Optional[X]`, `List[X]`, `Dict[X, Y]` from `typing` — never `X | None` (ruff `UP` rule is intentionally disabled repo-wide).
- Every new/modified function needs a docstring stating the fail-safe/default behavior, matching the existing style in `cli/loop.py` and `cli/cost.py`.
- `ruff check cli/ tests/` must pass with zero findings after every task.
- Sequential (non-`--team`) mode must remain **byte-identical** — `agent_cwd=None` is the only path it ever takes.
- No `.git` directory at the project root → worktree creation is skipped entirely (fail-safe, same discipline as graphify-absent / gate-defaults-WAKE); `--team` falls back to today's shared-workspace behavior for that run, not an error.
- A merge conflict is **never** auto-resolved — the worktree and branch are left on disk and surfaced via `CycleOutcome.merge_conflict`, mirroring the existing `contradiction` field's "surface, never auto-resolve" law.
- Full test suite (`python3 -m pytest tests/ -q`) must stay green after every task; run it at the end of every task, not just at the end of the plan.

---

### Task 1: `cli/worktree.py` — core primitives + real-git-repo tests

**Files:**
- Create: `cli/worktree.py`
- Test: `tests/test_worktree.py`

**Interfaces:**
- Produces (used by Task 2):
  - `worktree_path(project_root: Path, name: str) -> Path`
  - `is_git_repo(project_root: Path) -> bool`
  - `current_branch(project_root: Path, runner: Callable = subprocess.run) -> Optional[str]`
  - `ensure_worktrees_ignored(project_root: Path) -> None`
  - `@dataclass class WorktreeResult: ok: bool; path: Optional[Path] = None; error: Optional[str] = None`
  - `create_worktree(project_root: Path, name: str, base_branch: str, runner: Callable = subprocess.run) -> WorktreeResult`
  - `@dataclass class MergeResult: ok: bool; conflict: bool = False; error: Optional[str] = None`
  - `merge_worktree(project_root: Path, name: str, base_branch: str, runner: Callable = subprocess.run) -> MergeResult`
  - `remove_worktree(project_root: Path, name: str, force: bool = False, runner: Callable = subprocess.run) -> None`

- [ ] **Step 1: Write the failing tests for `is_git_repo` and `worktree_path`**

```python
# tests/test_worktree.py
from __future__ import annotations

import subprocess

import pytest

from cli.worktree import (
    MergeResult,
    WorktreeResult,
    create_worktree,
    current_branch,
    ensure_worktrees_ignored,
    is_git_repo,
    merge_worktree,
    remove_worktree,
    worktree_path,
)


def _run_git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path):
    """A real temp git repo with one commit on branch `main`, so worktree/merge
    tests exercise real git plumbing (no mocking of git itself)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(["init", "-b", "main"], repo)
    _run_git(["config", "user.email", "test@example.com"], repo)
    _run_git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("hello\n")
    _run_git(["add", "README.md"], repo)
    _run_git(["commit", "-m", "init"], repo)
    return repo


def test_worktree_path_is_dot_worktrees_under_root(tmp_path):
    assert worktree_path(tmp_path, "task-a") == tmp_path / ".worktrees" / "task-a"


def test_is_git_repo_true_for_real_repo(git_repo):
    assert is_git_repo(git_repo) is True


def test_is_git_repo_false_for_plain_dir(tmp_path):
    assert is_git_repo(tmp_path) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/navid.ghayazi/Desktop/project/private/sigma && python3 -m pytest tests/test_worktree.py -v`
Expected: `ModuleNotFoundError: No module named 'cli.worktree'` (or `ImportError` for the missing names).

- [ ] **Step 3: Write `cli/worktree.py` — path helpers + `is_git_repo` + `current_branch`**

```python
"""Real git-worktree isolation for sigma loop's --team mode.

`--team` runs N tasks CONCURRENTLY. Without this module, every task's agent
shares one working tree — a real collision risk when tasks touch overlapping
files. This module gives each task its own worktree + branch, mirroring
`cli/runner.py`'s AgentRunner split: pure logic here, `runner: Callable =
subprocess.run` injectable so tests never spawn a shell out of a real repo
unless they explicitly want to (see tests/test_worktree.py's real-git-repo
fixture — git itself is never mocked, only asserted against).

Fail-safe: `is_git_repo` gates every entry point that needs a real repo. No
`.git` at the project root → callers (cli/loop.py's run_loop) skip worktree
creation entirely and fall back to the shared-workspace behavior that existed
before this module — same discipline as graphify-absent or gate-defaults-WAKE.

A merge conflict is NEVER auto-resolved. `merge_worktree` returns
`conflict=True` and leaves the tree in its pre-merge state; the caller decides
what to do (cli/loop.py surfaces it via `CycleOutcome.merge_conflict` and
leaves the worktree+branch on disk for human resolution).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

WORKTREES_DIRNAME = ".worktrees"


def worktree_path(project_root: Path, name: str) -> Path:
    """Where a named worktree lives: `<project_root>/.worktrees/<name>`."""
    return project_root / WORKTREES_DIRNAME / name


def is_git_repo(project_root: Path) -> bool:
    """True if `project_root` has a `.git` (dir or file, e.g. a worktree's own
    gitdir pointer). Never raises — a permission error or odd filesystem state
    is treated as "not a git repo" (fail-safe gate for every other function)."""
    try:
        return (project_root / ".git").exists()
    except OSError:
        return False


def current_branch(project_root: Path, runner: Callable = subprocess.run) -> Optional[str]:
    """The repo's current branch name, or None if detached/unreadable/not a repo."""
    if not is_git_repo(project_root):
        return None
    try:
        proc = runner(
            ["git", "branch", "--show-current"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    name = (proc.stdout or "").strip()
    return name or None
```

- [ ] **Step 4: Run tests to verify the first three pass**

Run: `python3 -m pytest tests/test_worktree.py -v -k "worktree_path or is_git_repo"`
Expected: 2 passed (the `worktree_path` and `is_git_repo` tests). Import error on the rest is expected (not written yet).

- [ ] **Step 5: Commit**

```bash
git add cli/worktree.py tests/test_worktree.py
git commit -m "feat: cli/worktree.py path/detection primitives + real-git-repo test fixture"
```

- [ ] **Step 6: Write the failing test for `ensure_worktrees_ignored`**

```python
# append to tests/test_worktree.py
def test_ensure_worktrees_ignored_adds_and_commits_when_missing(git_repo):
    ensure_worktrees_ignored(git_repo)
    gitignore = git_repo / ".gitignore"
    assert gitignore.exists()
    assert ".worktrees/" in gitignore.read_text()
    # committed, not just written to disk
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(git_repo), capture_output=True, text=True
    )
    assert status.stdout.strip() == ""


def test_ensure_worktrees_ignored_noop_when_already_ignored(git_repo):
    (git_repo / ".gitignore").write_text(".worktrees/\n")
    _run_git(["add", ".gitignore"], git_repo)
    _run_git(["commit", "-m", "ignore worktrees"], git_repo)
    before = _run_git(["rev-parse", "HEAD"], git_repo)
    ensure_worktrees_ignored(git_repo)
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(git_repo), capture_output=True, text=True
    ).stdout
    # no new commit created — already ignored is a no-op
    assert after.strip() != ""
```

Note: `_run_git` in the second test doesn't return output today (it uses `check=True` without capturing meaningfully for reuse) — fix the helper to return the completed process so `before`/`rev-parse` comparisons work:

```python
def _run_git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )
```

(Apply this fix to the helper defined in Step 1 before running Step 6's tests.)

- [ ] **Step 7: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_worktree.py -v -k ensure_worktrees_ignored`
Expected: `ImportError` / `NameError` — `ensure_worktrees_ignored` not defined yet.

- [ ] **Step 8: Implement `ensure_worktrees_ignored`**

Append to `cli/worktree.py`:

```python
def ensure_worktrees_ignored(project_root: Path) -> None:
    """Add `.worktrees/` to .gitignore + commit, if not already ignored.

    Mirrors the vendored `using-git-worktrees` skill's own safety check: never
    let worktree contents get tracked. No-op (no commit) when already ignored.
    Fail-safe: if `project_root` isn't a git repo, does nothing (the caller,
    `create_worktree`, already gates on `is_git_repo` before calling this).
    """
    gitignore = project_root / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if f"{WORKTREES_DIRNAME}/" in existing or WORKTREES_DIRNAME in existing.splitlines():
        return
    new_content = existing
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    new_content += f"{WORKTREES_DIRNAME}/\n"
    gitignore.write_text(new_content)
    subprocess.run(["git", "add", ".gitignore"], cwd=str(project_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: ignore .worktrees/ (sigma --team isolation)"],
        cwd=str(project_root),
        check=True,
        capture_output=True,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_worktree.py -v`
Expected: all tests defined so far pass (5 total).

- [ ] **Step 10: Commit**

```bash
git add cli/worktree.py tests/test_worktree.py
git commit -m "feat: ensure_worktrees_ignored — gitignore + commit .worktrees/ safety check"
```

- [ ] **Step 11: Write the failing tests for `create_worktree`**

```python
# append to tests/test_worktree.py
def test_create_worktree_creates_branch_and_dir(git_repo):
    result = create_worktree(git_repo, "task-a", base_branch="main")
    assert result.ok is True
    assert result.path == worktree_path(git_repo, "task-a")
    assert result.path.is_dir()
    assert (result.path / "README.md").exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "task-a"], cwd=str(git_repo), capture_output=True, text=True
    ).stdout
    assert "task-a" in branches


def test_create_worktree_fails_gracefully_on_non_repo(tmp_path):
    result = create_worktree(tmp_path, "task-a", base_branch="main")
    assert result.ok is False
    assert result.path is None
    assert result.error is not None
```

- [ ] **Step 12: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_worktree.py -v -k create_worktree`
Expected: `NameError`/`AttributeError` — `create_worktree`/`WorktreeResult` not defined.

- [ ] **Step 13: Implement `WorktreeResult` + `create_worktree`**

Append to `cli/worktree.py`:

```python
@dataclass
class WorktreeResult:
    ok: bool
    path: Optional[Path] = None
    error: Optional[str] = None


def create_worktree(
    project_root: Path, name: str, base_branch: str, runner: Callable = subprocess.run
) -> WorktreeResult:
    """`git worktree add .worktrees/<name> -b <name> <base_branch>`.

    Ensures `.worktrees/` is gitignored first (best-effort — a failure there
    doesn't block worktree creation itself, it's a hygiene step not a gate).
    Fail-safe: not a git repo, or the git command errors, returns
    `ok=False, error=<message>` — never raises. Callers (run_loop) treat a
    failed create as "skip isolation for this task, fall back to agent_cwd=None".
    """
    if not is_git_repo(project_root):
        return WorktreeResult(ok=False, error=f"{project_root} is not a git repository")
    try:
        ensure_worktrees_ignored(project_root)
    except (OSError, subprocess.CalledProcessError):
        pass  # hygiene step; not fatal to worktree creation

    path = worktree_path(project_root, name)
    try:
        proc = runner(
            ["git", "worktree", "add", str(path), "-b", name, base_branch],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return WorktreeResult(ok=False, error=str(exc))
    if proc.returncode != 0:
        return WorktreeResult(ok=False, error=(proc.stderr or "").strip() or "git worktree add failed")
    return WorktreeResult(ok=True, path=path)
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_worktree.py -v`
Expected: all 7 tests pass.

- [ ] **Step 15: Commit**

```bash
git add cli/worktree.py tests/test_worktree.py
git commit -m "feat: create_worktree — real git worktree add with fail-safe non-repo handling"
```

- [ ] **Step 16: Write the failing tests for `merge_worktree` (clean merge + real conflict)**

```python
# append to tests/test_worktree.py
def test_merge_worktree_clean_merge_lands_commit(git_repo):
    create_worktree(git_repo, "task-a", base_branch="main")
    wt = worktree_path(git_repo, "task-a")
    (wt / "feature.txt").write_text("new feature\n")
    _run_git(["add", "feature.txt"], wt)
    _run_git(["commit", "-m", "add feature"], wt)

    result = merge_worktree(git_repo, "task-a", base_branch="main")
    assert result.ok is True
    assert result.conflict is False
    assert (git_repo / "feature.txt").exists()
    assert (git_repo / "feature.txt").read_text() == "new feature\n"


def test_merge_worktree_conflict_is_surfaced_not_resolved(git_repo):
    # Base branch changes README.md AFTER the worktree branched off it...
    create_worktree(git_repo, "task-a", base_branch="main")
    wt = worktree_path(git_repo, "task-a")
    (wt / "README.md").write_text("changed in worktree\n")
    _run_git(["add", "README.md"], wt)
    _run_git(["commit", "-m", "worktree edit"], wt)

    # ...main also edits the SAME line, so merging task-a back conflicts.
    (git_repo / "README.md").write_text("changed on main\n")
    _run_git(["add", "README.md"], git_repo)
    _run_git(["commit", "-m", "main edit"], git_repo)

    result = merge_worktree(git_repo, "task-a", base_branch="main")
    assert result.ok is False
    assert result.conflict is True
    # never auto-resolved: the conflict markers are present, nothing was force-picked
    assert "<<<<<<<" in (git_repo / "README.md").read_text()
    # abort the half-finished merge so the fixture repo isn't left mid-merge for
    # any test that runs after this one in the same file
    _run_git(["merge", "--abort"], git_repo)
```

- [ ] **Step 17: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_worktree.py -v -k merge_worktree`
Expected: `NameError` — `merge_worktree`/`MergeResult` not defined.

- [ ] **Step 18: Implement `MergeResult` + `merge_worktree`**

Append to `cli/worktree.py`:

```python
@dataclass
class MergeResult:
    ok: bool
    conflict: bool = False
    error: Optional[str] = None


def merge_worktree(
    project_root: Path, name: str, base_branch: str, runner: Callable = subprocess.run
) -> MergeResult:
    """`git merge --no-ff <name>` onto `base_branch`, run FROM `project_root`.

    Never auto-resolves a conflict: on conflict, returns `conflict=True` and
    leaves the tree exactly as git left it (conflict markers in place, merge
    in progress) — the caller (cli/loop.py) decides whether to surface it and
    leaves the worktree/branch on disk for a human. This function does NOT
    call `git merge --abort` on conflict; that decision belongs to the caller
    (tests that need a clean fixture afterward call it explicitly — see
    test_merge_worktree_conflict_is_surfaced_not_resolved).
    """
    if not is_git_repo(project_root):
        return MergeResult(ok=False, error=f"{project_root} is not a git repository")
    try:
        proc = runner(
            ["git", "merge", "--no-ff", name, "-m", f"Merge {name} (sigma --team)"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return MergeResult(ok=False, error=str(exc))
    if proc.returncode == 0:
        return MergeResult(ok=True)
    output = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
    conflict = "conflict" in output
    return MergeResult(ok=False, conflict=conflict, error=(proc.stderr or proc.stdout or "").strip())
```

- [ ] **Step 19: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_worktree.py -v`
Expected: all 9 tests pass.

- [ ] **Step 20: Commit**

```bash
git add cli/worktree.py tests/test_worktree.py
git commit -m "feat: merge_worktree — clean merge + conflict surfaced without auto-resolve"
```

- [ ] **Step 21: Write the failing tests for `remove_worktree`**

```python
# append to tests/test_worktree.py
def test_remove_worktree_removes_dir_and_branch(git_repo):
    create_worktree(git_repo, "task-a", base_branch="main")
    wt = worktree_path(git_repo, "task-a")
    assert wt.is_dir()

    remove_worktree(git_repo, "task-a", force=True)

    assert not wt.exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "task-a"], cwd=str(git_repo), capture_output=True, text=True
    ).stdout
    assert "task-a" not in branches


def test_remove_worktree_on_nonexistent_is_a_noop(git_repo):
    # Never created — must not raise.
    remove_worktree(git_repo, "never-existed", force=True)
```

- [ ] **Step 22: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_worktree.py -v -k remove_worktree`
Expected: `NameError` — `remove_worktree` not defined.

- [ ] **Step 23: Implement `remove_worktree`**

Append to `cli/worktree.py`:

```python
def remove_worktree(
    project_root: Path, name: str, force: bool = False, runner: Callable = subprocess.run
) -> None:
    """`git worktree remove` + `git branch -D <name>`.

    Best-effort cleanup: swallows errors from both commands (e.g. the worktree
    was never created, or was already removed) so a cleanup call never raises
    and never blocks the loop from reporting its outcome. `force=True` passes
    `--force` to `worktree remove` (used on a FAIL path, where uncommitted
    agent edits inside the worktree should not block cleanup).
    """
    if not is_git_repo(project_root):
        return
    path = worktree_path(project_root, name)
    remove_argv = ["git", "worktree", "remove", str(path)]
    if force:
        remove_argv.append("--force")
    try:
        runner(remove_argv, cwd=str(project_root), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        runner(
            ["git", "branch", "-D", name],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass
```

- [ ] **Step 24: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_worktree.py -v`
Expected: all 11 tests pass.

- [ ] **Step 25: Run ruff and the full suite**

Run: `python3 -m ruff check cli/worktree.py tests/test_worktree.py && python3 -m pytest tests/ -q`
Expected: `All checks passed!` and all existing + new tests pass (no regressions — `cli/worktree.py` is a brand-new module nothing else imports yet).

- [ ] **Step 26: Commit**

```bash
git add cli/worktree.py tests/test_worktree.py
git commit -m "feat: remove_worktree — best-effort cleanup, completes cli/worktree.py"
```

---

### Task 2: `cli/loop.py` — `agent_cwd` param on `execute_cycle` (byte-identical default)

**Files:**
- Modify: `cli/loop.py`
- Test: `tests/test_loop_exec.py`

**Interfaces:**
- Consumes: nothing new from Task 1 yet (this task only changes where the agent's `cwd` comes from — worktree wiring happens in Task 3).
- Produces (used by Task 3): `execute_cycle(..., agent_cwd: Optional[Path] = None)` — when `None`, every `.run(..., cwd=X)` call inside `execute_cycle`, `_run_verify`, and `_run_advisor_escalation` uses `workspace` exactly as today. When set, they use `agent_cwd` for the AGENT subprocess call, but artifact writes (`write_artifact(workspace / ...)`) stay pointed at `workspace` — unchanged.

- [ ] **Step 1: Write the failing test for `agent_cwd` behavior**

Add to `tests/test_loop_exec.py` (near the top-level tests, after `test_execute_cycle_pass`):

```python
def test_execute_cycle_agent_cwd_used_for_agent_calls_not_artifacts(tmp_path):
    agent_dir = tmp_path / "agent-dir"
    agent_dir.mkdir()
    artifact_dir = tmp_path / "artifact-dir"

    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])

    class CwdRecorder(ScriptedRunner):
        def __init__(self, results):
            super().__init__(results)
            self.cwds = []

        def run(self, prompt, cwd=None, role="agent"):
            self.cwds.append(cwd)
            return super().run(prompt, cwd=cwd, role=role)

    impl = CwdRecorder([AgentResult(ok=True, output="implemented")])
    chk = CwdRecorder([AgentResult(ok=True, output="VERDICT: PASS")])

    out = execute_cycle(plan, artifact_dir, artifact_dir / "skills", impl, chk, agent_cwd=agent_dir)

    assert out.verified is True
    # agents ran with cwd=agent_dir, NOT artifact_dir
    assert impl.cwds == [agent_dir]
    assert chk.cwds == [agent_dir]
    # artifacts still landed under artifact_dir (workspace), unchanged
    assert (artifact_dir / "impl" / f"{plan.worktree_name}.md").exists()
    assert (artifact_dir / "verify" / f"{plan.worktree_name}.md").exists()
    assert not (agent_dir / "impl").exists()


def test_execute_cycle_agent_cwd_none_falls_back_to_workspace(tmp_path):
    """Regression guard: agent_cwd=None (every existing caller) is byte-identical
    to today — the agent's cwd IS the workspace, same as before this param existed."""
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])

    class CwdRecorder(ScriptedRunner):
        def __init__(self, results):
            super().__init__(results)
            self.cwds = []

        def run(self, prompt, cwd=None, role="agent"):
            self.cwds.append(cwd)
            return super().run(prompt, cwd=cwd, role=role)

    impl = CwdRecorder([AgentResult(ok=True, output="implemented")])
    chk = CwdRecorder([AgentResult(ok=True, output="VERDICT: PASS")])

    execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk)  # agent_cwd default

    assert impl.cwds == [tmp_path]
    assert chk.cwds == [tmp_path]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k agent_cwd`
Expected: `TypeError: execute_cycle() got an unexpected keyword argument 'agent_cwd'` for the first test; the second test currently passes already (it's a pin of existing behavior) — that's fine, it documents intent even before the param exists.

- [ ] **Step 3: Add `agent_cwd` param to `execute_cycle` and thread it through**

In `cli/loop.py`, modify the `execute_cycle` signature (currently ends with `advisor_rounds: int = 1,`):

```python
def execute_cycle(
    plan: CyclePlan,
    workspace: Path,
    skills_dir: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner] = None,
    recall: str = "",
    test_writer: Optional[AgentRunner] = None,
    simplifier: Optional[AgentRunner] = None,
    advisor: Optional[AgentRunner] = None,
    advisor_rounds: int = 1,
    agent_cwd: Optional[Path] = None,
) -> CycleOutcome:
```

Add one line right after the existing distinctness-check block, before `title = plan.task.title`:

```python
    cwd = agent_cwd if agent_cwd is not None else workspace
```

Then replace every `cwd=workspace` passed to an agent `.run(...)` call inside `execute_cycle` itself with `cwd=cwd` — there are exactly two in `execute_cycle`'s body: the `test_writer.run(...)` call and the `implementer.run(...)` call. Do **not** touch any `write_artifact(workspace / ...)` call — those stay pointed at `workspace`.

Also update the docstring's final paragraph (the one already describing `advisor`) by appending:

```
    `agent_cwd`, when set, is where the implementer/verifier/logic/test-writer/
    simplifier/advisor subprocesses actually run (`cwd=` on every `.run()` call).
    `workspace` always stays where artifacts/logs/ratchets are written — the two
    are the same value (today's behavior) unless a caller splits them. `None`
    (every caller before --team) falls back to `workspace` — byte-identical.
```

Now update `_run_verify` to accept and use the same `cwd` (it currently hardcodes `cwd=workspace` on the `verifier.run` and `logic_checker.run` calls):

```python
def _run_verify(
    plan: CyclePlan,
    workspace: Path,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner],
    recall: str,
    cwd: Optional[Path] = None,
) -> tuple:
```

At the top of `_run_verify`'s body, add:

```python
    cwd = cwd if cwd is not None else workspace
```

Then change `verifier.run(..., cwd=workspace, ...)` → `verifier.run(..., cwd=cwd, ...)` and `logic_checker.run(..., cwd=workspace, ...)` → `logic_checker.run(..., cwd=cwd, ...)`. Leave both `write_artifact(workspace / "verify" / ...)` calls unchanged.

Update `_run_verify`'s docstring to add one line: `"cwd` is where the verifier/logic subprocess runs; `None` falls back to `workspace` (byte-identical to before this param existed)."

Now update both call sites of `_run_verify` inside `execute_cycle` to pass `cwd=cwd`:

```python
    passed, logic_ok, reason, detail = _run_verify(plan, workspace, verifier, logic_checker, recall, cwd=cwd)
```

Finally, update `_run_advisor_escalation` the same way — it also hardcodes `cwd=workspace` on the `advisor.run(...)` and `implementer.run(...)` calls, and calls `_run_verify` internally:

```python
def _run_advisor_escalation(
    plan: CyclePlan,
    workspace: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner],
    advisor: AgentRunner,
    advisor_rounds: int,
    reason: str,
    detail: str,
    recall: str,
    impl_output: str,
    outcome: CycleOutcome,
    cwd: Optional[Path] = None,
) -> tuple:
```

Add `cwd = cwd if cwd is not None else workspace` at the top, change the two `.run(..., cwd=workspace, ...)` calls to `cwd=cwd`, and change its internal `_run_verify(plan, workspace, verifier, logic_checker, recall)` call to `_run_verify(plan, workspace, verifier, logic_checker, recall, cwd=cwd)`.

Update `execute_cycle`'s call site of `_run_advisor_escalation` to pass `cwd=cwd`:

```python
        passed, reason = _run_advisor_escalation(
            plan, workspace, implementer, verifier, logic_checker,
            advisor, advisor_rounds, reason, detail, recall, impl.output, outcome,
            cwd=cwd,
        )
```

Note: `_run_simplify`'s two `.run(..., cwd=workspace, ...)` calls (simplifier + re-verify) are **intentionally left untouched** for this task — simplify only ever runs on the PASS path, after the escalation branch, and the spec does not require simplify to run inside a worktree for correctness (it operates on already-verified code and always re-verifies with the same `verifier` — extending it to `agent_cwd` is a reasonable future addition but out of scope here per YAGNI; nothing in Task 3 needs it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k agent_cwd`
Expected: both new tests pass.

- [ ] **Step 5: Run the full test file to confirm no regressions**

Run: `python3 -m pytest tests/test_loop_exec.py -v`
Expected: all tests pass (the existing ~50 tests in this file are unaffected since every one of them omits `agent_cwd`/`cwd`, hitting the `None` fallback).

- [ ] **Step 6: Run ruff and the full suite**

Run: `python3 -m ruff check cli/loop.py tests/test_loop_exec.py && python3 -m pytest tests/ -q`
Expected: clean, all green.

- [ ] **Step 7: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: execute_cycle gains agent_cwd param (defaults to workspace, byte-identical)"
```

---

### Task 3: `cli/loop.py` — `CycleOutcome.merge_conflict` + `run_loop`'s team+worktree branch

**Files:**
- Modify: `cli/loop.py`
- Test: `tests/test_loop_exec.py`

**Interfaces:**
- Consumes: `cli.worktree.create_worktree`, `merge_worktree`, `remove_worktree`, `current_branch`, `is_git_repo` (Task 1); `execute_cycle(..., agent_cwd=...)` (Task 2).
- Produces: `run_loop(..., worktrees: bool = True, project_root: Optional[Path] = None)`. `CycleOutcome.merge_conflict: Optional[Path] = None`.

- [ ] **Step 1: Write the failing test for `CycleOutcome.merge_conflict` default**

Add to `tests/test_loop_exec.py` near the `CycleOutcome` usages:

```python
def test_cycle_outcome_merge_conflict_defaults_to_none(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk)
    assert out.merge_conflict is None
```

- [ ] **Step 2: Run test to verify it currently passes trivially, then add the field**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k merge_conflict_defaults`
Expected: `AttributeError: 'CycleOutcome' object has no attribute 'merge_conflict'`.

Add the field to `CycleOutcome` in `cli/loop.py` (after `advisor_rounds_used`):

```python
    advisor_rounds_used: Optional[int] = None  # set only in --advisor mode
    merge_conflict: Optional[Path] = None  # --team + worktrees: set when a PASSing cycle's merge conflicts
    ratcheted_skill: Optional[Path] = None
```

Run again: `python3 -m pytest tests/test_loop_exec.py -v -k merge_conflict_defaults`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: CycleOutcome.merge_conflict field (default None, surfaced not auto-resolved)"
```

- [ ] **Step 4: Write the failing tests for `run_loop`'s team+worktree behavior (real temp git repo)**

Add to `tests/test_loop_exec.py`, in the "team mode" section, importing `cli.worktree` helpers at the top of the file:

```python
# add near the top of tests/test_loop_exec.py, alongside the existing imports
import subprocess as _subprocess

from cli.worktree import is_git_repo, worktree_path
```

Add a local fixture-style helper (not a pytest fixture, since it's only needed by a handful of tests in this file — keep it a plain function to avoid a new conftest dependency):

```python
def _init_git_repo(root):
    """Real minimal git repo with one commit on `main`, for team+worktree tests."""
    _subprocess.run(["git", "init", "-b", "main"], cwd=str(root), check=True, capture_output=True)
    _subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(root), check=True, capture_output=True)
    _subprocess.run(["git", "config", "user.name", "T"], cwd=str(root), check=True, capture_output=True)
    (root / "README.md").write_text("x\n")
    _subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True, capture_output=True)
    _subprocess.run(["git", "commit", "-m", "init"], cwd=str(root), check=True, capture_output=True)
```

Then the tests:

```python
def test_run_loop_team_with_worktrees_creates_and_merges_on_pass(tmp_path):
    _init_git_repo(tmp_path)

    class CwdRecorder(ScriptedRunner):
        def __init__(self, results):
            super().__init__(results)
            self.cwds = []

        def run(self, prompt, cwd=None, role="agent"):
            self.cwds.append(cwd)
            return super().run(prompt, cwd=cwd, role=role)

    seen_cwds = []

    def mk_impl():
        r = CwdRecorder([AgentResult(ok=True, output="i")])
        seen_cwds.append(r)
        return r

    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=mk_impl,
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
        project_root=tmp_path,
    )
    assert len(outcomes) == 2
    assert all(o.verified for o in outcomes)
    assert all(o.merge_conflict is None for o in outcomes)
    # each implementer ran inside its OWN worktree, not the shared tmp_path
    for recorder in seen_cwds:
        assert recorder.cwds[0] != tmp_path
        assert ".worktrees" in str(recorder.cwds[0])
    # worktrees are cleaned up after a successful merge
    assert not (tmp_path / ".worktrees").exists() or list((tmp_path / ".worktrees").iterdir()) == []
    # the merged content is on main
    log = _subprocess.run(
        ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
    ).stdout
    assert "Merge sigma-loop" in log or len(log.splitlines()) >= 1  # at least the merges landed


def test_run_loop_team_with_worktrees_removes_on_fail(tmp_path):
    _init_git_repo(tmp_path)
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: FAIL")]),
        team=True,
        project_root=tmp_path,
    )
    assert len(outcomes) == 2
    assert all(not o.verified for o in outcomes)
    # failed worktrees are removed, not left on disk
    worktrees_dir = tmp_path / ".worktrees"
    assert not worktrees_dir.exists() or list(worktrees_dir.iterdir()) == []


def test_run_loop_team_worktrees_false_reproduces_shared_workspace(tmp_path):
    """Regression guard: worktrees=False is byte-identical to team mode before
    this feature existed — every agent gets agent_cwd=None (i.e. `workspace`)."""
    _init_git_repo(tmp_path)

    class CwdRecorder(ScriptedRunner):
        def __init__(self, results):
            super().__init__(results)
            self.cwds = []

        def run(self, prompt, cwd=None, role="agent"):
            self.cwds.append(cwd)
            return super().run(prompt, cwd=cwd, role=role)

    seen = []

    def mk_impl():
        r = CwdRecorder([AgentResult(ok=True, output="i")])
        seen.append(r)
        return r

    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=mk_impl,
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
        worktrees=False,
        project_root=tmp_path,
    )
    assert len(outcomes) == 2
    for recorder in seen:
        assert recorder.cwds == [tmp_path]
    assert not (tmp_path / ".worktrees").exists()


def test_run_loop_team_no_git_repo_falls_back_gracefully(tmp_path):
    """No .git at all (existing pre-feature tests use plain tmp_path) — must
    still work exactly as before, agent_cwd=None for every task."""
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
        project_root=tmp_path,
    )
    assert len(outcomes) == 2
    assert all(o.verified for o in outcomes)


def test_run_loop_team_merge_conflict_is_surfaced(tmp_path):
    _init_git_repo(tmp_path)
    # Two tasks both edit README.md so their merges collide. Task order in
    # TASKS is deterministic (tokenize corpus, then train agent), and run_loop
    # preserves batch order in its results even under team=True.
    impl_outputs = iter(["edit one", "edit two"])

    def mk_impl():
        # Each implementer "edits" README.md inside its OWN worktree so the
        # two branches diverge from the same base commit and collide on merge.
        class Editor(ScriptedRunner):
            def run(self, prompt, cwd=None, role="agent"):
                if role == "implementer" and cwd is not None:
                    (cwd / "README.md").write_text(next(impl_outputs) + "\n")
                    _subprocess.run(
                        ["git", "add", "README.md"], cwd=str(cwd), check=True, capture_output=True
                    )
                    _subprocess.run(
                        ["git", "commit", "-m", "edit"], cwd=str(cwd), check=True, capture_output=True
                    )
                return super().run(prompt, cwd=cwd, role=role)
        return Editor([AgentResult(ok=True, output="i")])

    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=mk_impl,
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
        project_root=tmp_path,
    )
    assert len(outcomes) == 2
    # the SECOND task to merge collides with the first's already-merged edit.
    conflicts = [o for o in outcomes if o.merge_conflict is not None]
    assert len(conflicts) == 1
    # the conflicting worktree is left on disk for manual resolution
    assert conflicts[0].merge_conflict.exists()
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k "team_with_worktrees or team_no_git or team_merge_conflict"`
Expected: `TypeError: run_loop() got an unexpected keyword argument 'project_root'` (and `'worktrees'`).

- [ ] **Step 6: Implement the `run_loop` team+worktree branch**

In `cli/loop.py`, modify `run_loop`'s signature (currently ends with `team: bool = False, max_workers: int = 3,`):

```python
def run_loop(
    tasks: List[Task],
    workspace: Path,
    skills_dir: Path,
    max_cycles: int,
    make_implementer,
    make_verifier,
    make_logic_checker=None,
    gate: Optional[str] = None,
    make_test_writer=None,
    make_simplifier=None,
    make_advisor=None,
    advisor_rounds: int = 1,
    team: bool = False,
    max_workers: int = 3,
    worktrees: bool = True,
    project_root: Optional[Path] = None,
) -> List[CycleOutcome]:
```

Add to the docstring (after the existing `team` paragraph):

```
    `worktrees`, when True (the default) AND `team` is True AND `project_root`
    is a real git repository, gives each concurrent task its OWN git worktree
    + branch (see cli/worktree.py) instead of a shared working tree — real
    per-task isolation. Falls back to the pre-existing shared-workspace
    behavior (agent_cwd=None for every task) when: `team` is False (sequential
    mode never needs isolation), `worktrees=False` (explicit opt-out, e.g.
    `sigma.config.yml`'s `loop.worktrees: false`), or `project_root` has no
    `.git` (fail-safe — isolation requires a real repo to branch from).
    `project_root` defaults to `cli.paths.project_root()` when not passed
    (mirrors how the architecture-map injection below already resolves it).
    A PASSing cycle's worktree is merged back onto the branch `--team` started
    from; a merge conflict is surfaced via `CycleOutcome.merge_conflict` and
    the worktree/branch is LEFT ON DISK for manual resolution — never
    auto-resolved. A FAILing (or advisor-exhausted) cycle's worktree is
    removed directly.
```

Now find the existing block:

```python
    from cli.paths import project_root

    arch_block = arch_context(project_root())
```

Change it to use the new param instead of always calling the function, since the caller may have already supplied a `project_root`:

```python
    from cli.paths import project_root as _resolve_project_root

    root = project_root if project_root is not None else _resolve_project_root()
    arch_block = arch_context(root)
```

Then find the `team` branch at the very end of `run_loop`:

```python
    if team:
        # Independent tasks run concurrently; preserve batch order in results.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(run_one, batch))

    return [run_one(task) for task in batch]
```

Replace it with:

```python
    if team:
        use_worktrees = worktrees and _team_worktrees_available(root)
        if use_worktrees:
            return _run_team_with_worktrees(batch, root, run_one)
        # Independent tasks run concurrently in the SHARED workspace (no real
        # isolation) — either worktrees were disabled/unavailable, or root has
        # no .git. Preserves the exact pre-feature behavior.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            return list(pool.map(run_one, batch))

    return [run_one(task) for task in batch]
```

Now `run_one` needs to accept an `agent_cwd` and thread it into `execute_cycle`. Find:

```python
    def run_one(task: Task) -> CycleOutcome:
        plan = plan_cycle(task)
        return execute_cycle(
            plan, workspace, skills_dir,
            make_implementer(), make_verifier(),
            make_logic_checker() if make_logic_checker else None,
            recall=recall_cache.get(plan.implementer_domain, ""),
            test_writer=make_test_writer() if make_test_writer else None,
            simplifier=make_simplifier() if make_simplifier else None,
            advisor=make_advisor() if make_advisor else None,
            advisor_rounds=advisor_rounds,
        )
```

Replace it with:

```python
    def run_one(task: Task, agent_cwd: Optional[Path] = None) -> CycleOutcome:
        plan = plan_cycle(task)
        return execute_cycle(
            plan, workspace, skills_dir,
            make_implementer(), make_verifier(),
            make_logic_checker() if make_logic_checker else None,
            recall=recall_cache.get(plan.implementer_domain, ""),
            test_writer=make_test_writer() if make_test_writer else None,
            simplifier=make_simplifier() if make_simplifier else None,
            advisor=make_advisor() if make_advisor else None,
            advisor_rounds=advisor_rounds,
            agent_cwd=agent_cwd,
        )
```

Add two new module-level helper functions right before `run_loop` (after `record_cycle_steps`, so they're near the other small pure-ish helpers):

```python
def _team_worktrees_available(project_root: Path) -> bool:
    """True if real per-task worktree isolation can be attempted."""
    from cli.worktree import is_git_repo

    return is_git_repo(project_root)


def _run_team_with_worktrees(batch: List[Task], project_root: Path, run_one) -> List[CycleOutcome]:
    """Run `batch` concurrently, each task in its own git worktree.

    Creates one worktree per task BEFORE fan-out (sequential, so worktree
    creation itself never races). After each outcome: PASS → merge (conflict
    surfaced via `outcome.merge_conflict`, worktree left on disk; clean merge
    → worktree removed). FAIL → worktree removed directly. A task whose
    worktree fails to CREATE falls back to `agent_cwd=None` for that one task
    only (best-effort — one bad worktree never blocks the rest of the batch).
    """
    from concurrent.futures import ThreadPoolExecutor

    from cli.worktree import create_worktree, current_branch, merge_worktree, remove_worktree

    base_branch = current_branch(project_root) or "main"
    plans = [plan_cycle(task) for task in batch]
    created: Dict[str, Path] = {}
    for plan in plans:
        result = create_worktree(project_root, plan.worktree_name, base_branch)
        if result.ok:
            created[plan.worktree_name] = result.path

    def run_with_isolation(task: Task) -> CycleOutcome:
        plan = plan_cycle(task)
        agent_cwd = created.get(plan.worktree_name)
        outcome = run_one(task, agent_cwd=agent_cwd)
        if agent_cwd is None:
            return outcome
        if outcome.verified:
            merge = merge_worktree(project_root, plan.worktree_name, base_branch)
            if merge.ok:
                remove_worktree(project_root, plan.worktree_name)
            elif merge.conflict:
                outcome.merge_conflict = agent_cwd
                # left on disk for manual resolution — never removed on conflict
            else:
                # a non-conflict merge failure (e.g. git error) — remove rather
                # than leak a worktree for a problem a human can't resolve by
                # inspecting it; the ratchet/verified outcome already stands.
                remove_worktree(project_root, plan.worktree_name, force=True)
        else:
            remove_worktree(project_root, plan.worktree_name, force=True)
        return outcome

    with ThreadPoolExecutor(max_workers=len(batch) or 1) as pool:
        return list(pool.map(run_with_isolation, batch))
```

Note: `max_workers=len(batch) or 1` intentionally does not reuse the outer `max_workers` param — each task already has its own isolated worktree, so there is no reason to cap concurrency below the batch size here (the original `max_workers=3` default exists for the shared-workspace fallback path, where unbounded concurrency against one tree would be worse). Add this as a one-line comment above the `ThreadPoolExecutor` call:

```python
    # Unlike the shared-workspace fallback, each task has its own worktree, so
    # there's no reason to cap concurrency below the batch size.
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k "team_with_worktrees or team_no_git or team_merge_conflict or team_worktrees_false"`
Expected: all 5 new tests pass. If `test_run_loop_team_merge_conflict_is_surfaced` is flaky on task ordering, re-read `run_loop`'s batch-order guarantee (`pool.map` preserves input order in its return list) — the test's assumption that exactly one of the two outcomes gets `merge_conflict` set should hold regardless of which of the two tasks' merge lands first, since both edit the same line of the same file relative to the same base commit.

- [ ] **Step 8: Run the existing team tests to confirm no regressions**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k "team"`
Expected: `test_run_loop_team_runs_all_tasks`, `test_run_loop_team_respects_budget`, `test_run_loop_team_plus_tdd` (pre-existing, using plain `tmp_path` with no `.git`) all still pass — they hit the `_team_worktrees_available` → `False` → shared-workspace fallback path, unchanged from before this task.

- [ ] **Step 9: Run ruff and the full suite**

Run: `python3 -m ruff check cli/loop.py tests/test_loop_exec.py && python3 -m pytest tests/ -q`
Expected: clean, all green (should now be north of 645 tests given Tasks 1–3's additions).

- [ ] **Step 10: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: run_loop --team gets real per-task worktree isolation with surfaced merge conflicts"
```

---

### Task 4: `cli/config.py` — wire up the dead `worktrees` flag + `cmd_loop` wiring

**Files:**
- Modify: `cli/config.py` (no code change needed — the field already exists and round-trips; this task is about USING it)
- Modify: `cli/main.py`
- Test: `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `cfg.loop.worktrees: bool` (already exists in `LoopConfig`), `run_loop(..., worktrees=..., project_root=...)` (Task 3).

- [ ] **Step 1: Write the failing test confirming `LoopConfig.worktrees` round-trips (documents it's no longer dead)**

Add to `tests/test_config.py` (check the file first for its existing import/fixture style, then append in the same style):

```python
def test_loop_worktrees_round_trips_false(tmp_path):
    cfg = SigmaConfig()
    cfg.loop.worktrees = False
    write_config(cfg, root=tmp_path)
    loaded = load_config(root=tmp_path)
    assert loaded.loop.worktrees is False


def test_loop_worktrees_defaults_true(tmp_path):
    cfg = SigmaConfig()
    write_config(cfg, root=tmp_path)
    loaded = load_config(root=tmp_path)
    assert loaded.loop.worktrees is True
```

(If `tests/test_config.py` doesn't already import `SigmaConfig`, `write_config`, `load_config`, add those imports at the top matching however the existing tests in that file import from `cli.config`.)

- [ ] **Step 2: Run tests to verify they pass immediately**

Run: `python3 -m pytest tests/test_config.py -v -k worktrees`
Expected: both PASS already — `LoopConfig.worktrees` already round-trips correctly (confirmed by reading `cli/config.py`'s `to_dict`/`_from_dict`), it was only ever dead because nothing downstream READ it. This step is a documentation/regression-lock, not a bug fix.

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: lock LoopConfig.worktrees round-trip (was declared but unread before this feature)"
```

- [ ] **Step 4: Wire `cfg.loop.worktrees` into `cmd_loop`**

In `cli/main.py`, find `cmd_loop`'s `run_loop(...)` call (currently ending with `team=args.team, gate=args.gate,`):

```python
    with keep_awake(enabled=args.keep_awake):
        outcomes = run_loop(
            tasks,
            ws,
            skills_dir,
            cfg.loop.max_cycles,
            make_implementer=lambda: _make(routes.get("implement")),
            make_verifier=lambda: _make(routes.get("verify")),
            make_logic_checker=(lambda: _make(routes.get("logic"))) if args.logic else None,
            make_test_writer=(lambda: _make(routes.get("verify"))) if args.tdd else None,
            make_simplifier=(lambda: _make(routes.get("implement"))) if args.simplify else None,
            make_advisor=(lambda: _make(advisor_model)) if args.advisor else None,
            advisor_rounds=args.advisor_rounds,
            team=args.team,
            gate=args.gate,
        )
```

Add `worktrees=cfg.loop.worktrees,` and `project_root=project_root(),` (importing `project_root` from `cli.paths` — check the existing `from cli.paths import DOMAINS, sigma_home, spec_workspace` import at the top of `cli/main.py` and add `project_root` to it):

```python
    with keep_awake(enabled=args.keep_awake):
        outcomes = run_loop(
            tasks,
            ws,
            skills_dir,
            cfg.loop.max_cycles,
            make_implementer=lambda: _make(routes.get("implement")),
            make_verifier=lambda: _make(routes.get("verify")),
            make_logic_checker=(lambda: _make(routes.get("logic"))) if args.logic else None,
            make_test_writer=(lambda: _make(routes.get("verify"))) if args.tdd else None,
            make_simplifier=(lambda: _make(routes.get("implement"))) if args.simplify else None,
            make_advisor=(lambda: _make(advisor_model)) if args.advisor else None,
            advisor_rounds=args.advisor_rounds,
            team=args.team,
            worktrees=cfg.loop.worktrees,
            project_root=project_root(),
            gate=args.gate,
        )
```

Add a status print alongside the existing `if args.team:` line:

```python
    if args.team:
        _print("  👥 team mode: independent tasks run in parallel")
        _print(f"  🌳 worktree isolation: {'on' if cfg.loop.worktrees else 'off (sigma.config.yml)'}")
```

- [ ] **Step 5: Add the merge-conflict output line**

In `cmd_loop`'s outcome-printing loop, find:

```python
        if o.advised is not None:
            rounds = o.advisor_rounds_used or 0
            _print(f"    advisor: {'✓ rescued in ' + str(rounds) + ' round(s)' if o.advised else '✗ exhausted (' + str(rounds) + ' round(s)) — reverted'}")
        if o.ratcheted_skill:
```

Add a `merge_conflict` line right after the `advised` block:

```python
        if o.advised is not None:
            rounds = o.advisor_rounds_used or 0
            _print(f"    advisor: {'✓ rescued in ' + str(rounds) + ' round(s)' if o.advised else '✗ exhausted (' + str(rounds) + ' round(s)) — reverted'}")
        if o.merge_conflict:
            _print(f"    ⚠ merge conflict — branch left at {o.merge_conflict} for manual resolution")
        if o.ratcheted_skill:
```

- [ ] **Step 6: Run the argparse/cli test suite**

Run: `python3 -m pytest tests/test_cli.py -v -k loop`
Expected: all existing loop-related argparse tests still pass (no new flags added in this task — `worktrees` is config-driven, not a new CLI flag, matching the spec's "a project sets `worktrees: false` in `sigma.config.yml`" design).

- [ ] **Step 7: Run ruff and the full suite**

Run: `python3 -m ruff check cli/ tests/ && python3 -m pytest tests/ -q`
Expected: clean, all green.

- [ ] **Step 8: Commit**

```bash
git add cli/main.py tests/test_config.py
git commit -m "feat: wire cfg.loop.worktrees into cmd_loop; print merge-conflict outcomes"
```

---

### Task 5: Live functional verification (real subprocess, real git, scratch repo — not just pytest)

**Files:** none modified — this task is verification only, using a disposable `/tmp` scratch repo and a scripted fake `claude` shim (same technique already proven earlier in this session for the `--advisor` axis).

- [ ] **Step 1: Set up a real scratch git repo + fake claude shim**

```bash
mkdir -p /tmp/sigma-worktree-e2e/sigma/specs/2026-07-04-demo
cd /tmp/sigma-worktree-e2e
git init -b main
git config user.email "t@example.com"
git config user.name "T"
cat > sigma.config.yml <<'EOF'
profile:
  name: sigma-worktree-e2e
research:
  models: [claude]
domains: [nlp]
commands: []
loop:
  max_cycles: 20
  worktrees: true
  maker_checker_separation: true
EOF
mkdir -p sigma/specs/2026-07-04-demo
cat > sigma/specs/2026-07-04-demo/tasks.md <<'EOF'
- [ ] T1 (nlp): tokenize corpus
- [ ] T2 (nlp): train classifier
EOF
git add -A
git commit -m "init scratch repo"

mkdir -p /tmp/fake-claude-bin
cat > /tmp/fake-claude-bin/claude <<'SCRIPT'
#!/bin/bash
LOG=/tmp/sigma-worktree-e2e/fake-claude-calls.log
echo "argv: $@ | cwd=$(pwd)" >> "$LOG"
echo "VERDICT: PASS"
exit 0
SCRIPT
chmod +x /tmp/fake-claude-bin/claude
```

- [ ] **Step 2: Run `sigma loop --execute --team` against the scratch repo**

```bash
mkdir -p /tmp/sigma-worktree-e2e/fake-sigma-home/skills
cd /tmp/sigma-worktree-e2e
SIGMA_HOME=/tmp/sigma-worktree-e2e/fake-sigma-home \
  PATH=/tmp/fake-claude-bin:$PATH \
  PYTHONPATH=/Users/navid.ghayazi/Desktop/project/private/sigma \
  python3 -m cli.main loop --topic demo --execute --team
```

Expected output includes `🌳 worktree isolation: on` and both tasks reported `✓ ran 2 cycle(s): 2 passed, 0 failed`.

- [ ] **Step 3: Verify the argv log shows two DIFFERENT cwds, both under `.worktrees/`**

```bash
cat /tmp/sigma-worktree-e2e/fake-claude-calls.log
```

Expected: at least two distinct `cwd=/tmp/sigma-worktree-e2e/.worktrees/sigma-loop-*` paths, never `cwd=/tmp/sigma-worktree-e2e` itself.

- [ ] **Step 4: Verify worktrees were cleaned up after the successful run**

```bash
ls /tmp/sigma-worktree-e2e/.worktrees/ 2>&1
git -C /tmp/sigma-worktree-e2e worktree list
git -C /tmp/sigma-worktree-e2e log --oneline
```

Expected: `.worktrees/` is empty or absent; `git worktree list` shows only the main worktree; `git log` shows the two `Merge sigma-loop-* (sigma --team)` commits landed on `main`.

- [ ] **Step 5: Verify the real repo (sigma itself) was never touched**

```bash
git -C /Users/navid.ghayazi/Desktop/project/private/sigma status --short
```

Expected: no unexpected changes — only whatever this plan's own tasks committed on `feat/team-worktree-isolation`.

- [ ] **Step 6: Clean up the scratch environment**

```bash
rm -rf /tmp/sigma-worktree-e2e /tmp/fake-claude-bin
```

- [ ] **Step 7: Final full-suite + ruff pass on the real repo**

```bash
cd /Users/navid.ghayazi/Desktop/project/private/sigma
python3 -m ruff check cli/ tests/
python3 -m pytest tests/ -q
```

Expected: `All checks passed!` and every test green.

- [ ] **Step 8: Update `docs/superpowers/specs/2026-07-04-team-worktree-isolation-design.md`'s status line**

Change `**Status:** approved (brainstorm → plan), ready to implement` to `**Status:** implemented and verified (live functional test + full suite green)`.

```bash
git add docs/superpowers/specs/2026-07-04-team-worktree-isolation-design.md
git commit -m "docs: mark --team worktree isolation spec as implemented and verified"
```

---

## Post-plan (outside this plan's scope, handled by the user's stated end-to-end goal)

After Task 5, the branch `feat/team-worktree-isolation` is implemented, tested, and live-verified. Per the user's stated goal, the remaining steps — push, open/merge a PR to `main` on `navidgh66/sigma`, and cut a version release — are release-process steps, not implementation-plan steps. Use the `gh-account-keychain-workaround` memory (per-command `gh auth token -u navidgh66` override) for every push/PR/merge command, and bump `cli/__init__.py`'s `__version__` (currently `0.14.0`) following the exact pattern of the most recent version-bump commits (`fa660c1 chore: bump version to 0.14.0 (sigma setup-repo)`) before tagging/releasing.
