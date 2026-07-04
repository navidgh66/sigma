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
