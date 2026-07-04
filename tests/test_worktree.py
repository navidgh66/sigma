from __future__ import annotations

import subprocess

import pytest

from cli.worktree import (
    create_worktree,
    current_branch,
    ensure_worktrees_ignored,
    is_git_repo,
    merge_worktree,
    remove_worktree,
    worktree_path,
)


def _run_git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


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


def test_current_branch_returns_real_branch_name(git_repo):
    assert current_branch(git_repo) == "main"


def test_current_branch_none_for_non_repo(tmp_path):
    assert current_branch(tmp_path) is None


def test_ensure_worktrees_ignored_adds_and_commits_when_missing(git_repo):
    ensure_worktrees_ignored(git_repo)
    gitignore = git_repo / ".gitignore"
    assert gitignore.exists()
    assert ".worktrees/" in gitignore.read_text()
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
    assert after.strip() == before.stdout.strip()  # no new commit created — no-op


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
    create_worktree(git_repo, "task-a", base_branch="main")
    wt = worktree_path(git_repo, "task-a")
    (wt / "README.md").write_text("changed in worktree\n")
    _run_git(["add", "README.md"], wt)
    _run_git(["commit", "-m", "worktree edit"], wt)

    (git_repo / "README.md").write_text("changed on main\n")
    _run_git(["add", "README.md"], git_repo)
    _run_git(["commit", "-m", "main edit"], git_repo)

    result = merge_worktree(git_repo, "task-a", base_branch="main")
    assert result.ok is False
    assert result.conflict is True
    assert "<<<<<<<" in (git_repo / "README.md").read_text()
    _run_git(["merge", "--abort"], git_repo)


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
    remove_worktree(git_repo, "never-existed", force=True)
