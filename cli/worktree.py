"""Git worktree management for isolated, parallel-safe loop cycles.

Each loop task runs in its own worktree so concurrent agents never collide on
files. `git_run` is injectable so the logic is testable without touching git.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


@dataclass
class WorktreeResult:
    ok: bool
    path: Optional[Path]
    error: Optional[str] = None


def _default_git(argv: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *argv],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


@dataclass
class WorktreeManager:
    """Create/remove git worktrees under a base dir. `git_run` is injectable."""

    repo_root: Path
    base_dir: Optional[Path] = None
    git_run: Callable = _default_git

    def _worktrees_root(self) -> Path:
        return self.base_dir or (self.repo_root / ".sigma" / "worktrees")

    def create(self, name: str, branch: Optional[str] = None) -> WorktreeResult:
        """Create a worktree named `name`, on a new branch (default: name)."""
        target = self._worktrees_root() / name
        branch = branch or f"sigma/{name}"
        argv = ["worktree", "add", "-b", branch, str(target)]
        proc = self.git_run(argv, cwd=self.repo_root)
        if proc.returncode != 0:
            return WorktreeResult(ok=False, path=None, error=(proc.stderr or "").strip())
        return WorktreeResult(ok=True, path=target)

    def remove(self, name: str, force: bool = True) -> WorktreeResult:
        """Remove a worktree by name."""
        target = self._worktrees_root() / name
        argv = ["worktree", "remove", str(target)]
        if force:
            argv.append("--force")
        proc = self.git_run(argv, cwd=self.repo_root)
        if proc.returncode != 0:
            return WorktreeResult(ok=False, path=target, error=(proc.stderr or "").strip())
        return WorktreeResult(ok=True, path=target)
