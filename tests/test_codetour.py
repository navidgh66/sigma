"""Tests for cli.codetour — pure .tour validation against a fake repo."""

from __future__ import annotations

from cli.codetour import validate_tour


def _repo(tmp_path):
    (tmp_path / "a.py").write_text("line1\nline2\ntarget here\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "b.py").write_text("def foo():\n    return 1\n")
    return tmp_path


def test_valid_tour_has_no_problems(tmp_path):
    repo = _repo(tmp_path)
    tour = {
        "title": "Tour",
        "steps": [
            {"description": "intro"},
            {"description": "look", "file": "a.py", "line": 3},
            {"description": "pat", "file": "a.py", "pattern": "target here"},
            {"description": "fn", "file": "pkg/b.py", "line": 1},
        ],
    }
    assert validate_tour(tour, repo) == []


def test_missing_title(tmp_path):
    problems = validate_tour({"steps": [{"description": "x"}]}, tmp_path)
    assert any("title" in p for p in problems)


def test_empty_steps(tmp_path):
    problems = validate_tour({"title": "T", "steps": []}, tmp_path)
    assert any("steps" in p for p in problems)


def test_missing_file_flagged(tmp_path):
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "ghost.py", "line": 1}]}
    problems = validate_tour(tour, repo)
    assert any("file not found" in p for p in problems)


def test_line_out_of_range(tmp_path):
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "a.py", "line": 999}]}
    problems = validate_tour(tour, repo)
    assert any("out of range" in p for p in problems)


def test_line_zero_out_of_range(tmp_path):
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "a.py", "line": 0}]}
    problems = validate_tour(tour, repo)
    assert any("out of range" in p for p in problems)


def test_pattern_not_found(tmp_path):
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "a.py", "pattern": "nope"}]}
    problems = validate_tour(tour, repo)
    assert any("pattern not found" in p for p in problems)


def test_step_missing_description(tmp_path):
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"file": "a.py", "line": 1}]}
    problems = validate_tour(tour, repo)
    assert any("description" in p for p in problems)


def test_description_only_step_ok(tmp_path):
    # A step with no file (pure narration) is valid.
    assert validate_tour({"title": "T", "steps": [{"description": "hi"}]}, tmp_path) == []


def test_bool_line_rejected(tmp_path):
    # `True` is an int subclass — must not be accepted as a line number.
    repo = _repo(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "a.py", "line": True}]}
    problems = validate_tour(tour, repo)
    assert any("integer" in p for p in problems)
