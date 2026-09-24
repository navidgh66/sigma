"""Tests for scripts/test_guard.py (implementer must not edit existing tests)."""

import importlib.util
import json
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "test_guard.py"
_spec = importlib.util.spec_from_file_location("test_guard", _PATH)
tg = importlib.util.module_from_spec(_spec)
sys.modules["test_guard"] = tg
_spec.loader.exec_module(tg)


def test_is_test_path():
    for p in ["tests/test_a.py", "pkg/test_b.py", "pkg/b_test.py", "web/a.test.ts",
              "web/a.spec.js", "tests/fixtures/data.json"]:
        assert tg.is_test_path(p), p
    for p in ["src/a.py", "src/contest.py", "docs/testing.md"]:
        assert not tg.is_test_path(p), p


def _repo(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("assert 1\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "a.test.js").write_text("")
    return tmp_path


def test_snapshot_only_test_files_and_skips_vendor_dirs(tmp_path):
    snap = tg.snapshot(_repo(tmp_path))
    assert list(snap) == ["tests/test_a.py"]


def test_check_flags_edit_and_delete_allows_new(tmp_path):
    root = _repo(tmp_path)
    before = tg.snapshot(root)
    (root / "tests" / "test_new.py").write_text("assert 2\n")  # new: allowed
    (root / "src" / "a.py").write_text("x = 2\n")             # not a test: ignored
    assert tg.check(before, root) == []
    (root / "tests" / "test_a.py").write_text("assert True\n")  # edited
    assert tg.check(before, root) == ["tests/test_a.py"]
    (root / "tests" / "test_a.py").unlink()                      # deleted
    assert tg.check(before, root) == ["tests/test_a.py"]


def test_cli_round_trip(tmp_path, capsys):
    root = _repo(tmp_path)
    snap_file = tmp_path / "snap.json"
    assert tg.cli(["snapshot", str(snap_file), "--root", str(root)]) == 0
    assert json.loads(snap_file.read_text())["tests/test_a.py"]
    assert tg.cli(["check", str(snap_file), "--root", str(root)]) == 0
    (root / "tests" / "test_a.py").write_text("changed\n")
    assert tg.cli(["check", str(snap_file), "--root", str(root)]) == 1
    assert "tests/test_a.py" in capsys.readouterr().out


def test_top_level_sigma_workspace_skipped_but_nested_sigma_package_kept(tmp_path):
    (tmp_path / "sigma" / "specs").mkdir(parents=True)
    (tmp_path / "sigma" / "specs" / "test_x.py").write_text("")
    (tmp_path / "src" / "sigma" / "tests").mkdir(parents=True)
    (tmp_path / "src" / "sigma" / "tests" / "test_y.py").write_text("")
    assert list(tg.snapshot(tmp_path)) == ["src/sigma/tests/test_y.py"]


def test_restore_puts_back_edited_and_deleted_tests(tmp_path):
    root = _repo(tmp_path)
    (root / "tests" / "test_b.py").write_text("assert 2\n")
    backup = tmp_path / "backup"
    before = tg.snapshot(root, backup_dir=backup)
    (root / "tests" / "test_a.py").write_text("gutted\n")
    (root / "tests" / "test_b.py").unlink()
    (root / "tests" / "test_new.py").write_text("new\n")
    assert tg.restore(before, root, backup) == ["tests/test_a.py", "tests/test_b.py"]
    assert (root / "tests" / "test_a.py").read_text() == "assert 1\n"
    assert (root / "tests" / "test_b.py").read_text() == "assert 2\n"
    assert (root / "tests" / "test_new.py").exists()  # new tests are left alone
    assert tg.check(before, root) == []


def test_cli_snapshot_keeps_backup_and_restore_round_trip(tmp_path, capsys):
    root = _repo(tmp_path)
    snap_file = tmp_path / "snap.json"
    assert tg.cli(["snapshot", str(snap_file), "--root", str(root)]) == 0
    (root / "tests" / "test_a.py").write_text("changed\n")
    assert tg.cli(["restore", str(snap_file), "--root", str(root)]) == 0
    assert "tests/test_a.py" in capsys.readouterr().out
    assert tg.cli(["check", str(snap_file), "--root", str(root)]) == 0
