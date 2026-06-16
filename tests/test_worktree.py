
from cli.worktree import WorktreeManager


def _ok_git(captured):
    def git(argv, cwd=None):
        captured.append((argv, cwd))

        class P:
            returncode = 0
            stdout = ""
            stderr = ""

        return P()

    return git


def _fail_git(stderr):
    def git(argv, cwd=None):
        class P:
            returncode = 1
            stdout = ""

        P.stderr = stderr
        return P()

    return git


def test_create_invokes_git(tmp_path):
    captured = []
    mgr = WorktreeManager(repo_root=tmp_path, git_run=_ok_git(captured))
    res = mgr.create("task-1")
    assert res.ok is True
    argv, cwd = captured[0]
    assert argv[:3] == ["worktree", "add", "-b"]
    assert cwd == tmp_path
    assert res.path == tmp_path / ".sigma" / "worktrees" / "task-1"


def test_create_failure(tmp_path):
    mgr = WorktreeManager(repo_root=tmp_path, git_run=_fail_git("already exists"))
    res = mgr.create("dup")
    assert res.ok is False
    assert "already exists" in (res.error or "")


def test_remove_invokes_git(tmp_path):
    captured = []
    mgr = WorktreeManager(repo_root=tmp_path, git_run=_ok_git(captured))
    res = mgr.remove("task-1")
    assert res.ok is True
    argv, _ = captured[0]
    assert argv[:2] == ["worktree", "remove"]
    assert "--force" in argv


def test_custom_base_dir(tmp_path):
    captured = []
    base = tmp_path / "wts"
    mgr = WorktreeManager(repo_root=tmp_path, base_dir=base, git_run=_ok_git(captured))
    res = mgr.create("x")
    assert res.path == base / "x"
