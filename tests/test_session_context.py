"""Tests for cli.session_context — the pure pointer builder (read side of learn).

`build_pointer` names the durable learn artifacts (ARCHITECTURE.md + .tours/*.tour)
so a SessionStart hook can nudge every new Claude Code session to read them. When
nothing has been learned yet it returns a lazy hint instead. It never raises.
"""

from __future__ import annotations

from cli import session_context as sc


def _make_tour(root):
    tours = root / ".tours"
    tours.mkdir(parents=True, exist_ok=True)
    (tours / "codebase.tour").write_text("{}")


# --------------------------- both artifacts present --------------------------- #
def test_pointer_names_both_artifacts(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n")
    _make_tour(tmp_path)
    out = sc.build_pointer(tmp_path)
    assert "ARCHITECTURE.md" in out
    assert ".tours/codebase.tour" in out
    # It's a pointer, not a dump — the architecture body must not be inlined.
    assert "# Arch" not in out


def test_pointer_lists_multiple_tours(tmp_path):
    tours = tmp_path / ".tours"
    tours.mkdir()
    (tours / "a.tour").write_text("{}")
    (tours / "b.tour").write_text("{}")
    out = sc.build_pointer(tmp_path)
    assert ".tours/a.tour" in out
    assert ".tours/b.tour" in out


# --------------------------- only one present --------------------------- #
def test_pointer_arch_only(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n")
    out = sc.build_pointer(tmp_path)
    assert "ARCHITECTURE.md" in out
    assert ".tour" not in out


def test_pointer_tour_only(tmp_path):
    _make_tour(tmp_path)
    out = sc.build_pointer(tmp_path)
    assert ".tours/codebase.tour" in out
    assert "ARCHITECTURE.md" not in out


# --------------------------- nothing learned yet --------------------------- #
def test_pointer_lazy_hint_when_absent(tmp_path):
    out = sc.build_pointer(tmp_path)
    assert "/learn" in out  # nudge to run the learn stage
    assert "ARCHITECTURE.md" not in out


def test_pointer_always_nonempty(tmp_path):
    # The hook always emits something — either pointers or the lazy hint.
    assert sc.build_pointer(tmp_path).strip()


# --------------------------- never raises --------------------------- #
def test_pointer_missing_root_is_hint_not_raise(tmp_path):
    out = sc.build_pointer(tmp_path / "does-not-exist")
    assert "/learn" in out  # degrades to the lazy hint, no exception


def test_pointer_tours_not_a_dir_is_tolerated(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\n")
    (tmp_path / ".tours").write_text("i am a file, not a dir")  # pathological
    out = sc.build_pointer(tmp_path)
    assert "ARCHITECTURE.md" in out  # still works, no crash


# --------------------------- arch_context (inject map into CLI prompts) --------------------------- #
def test_arch_context_empty_when_absent(tmp_path):
    assert sc.arch_context(tmp_path) == ""  # no ARCHITECTURE.md → byte-identical no-op


def test_arch_context_includes_map(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("# Arch\nentry: cli/main.py\n")
    out = sc.arch_context(tmp_path)
    assert "entry: cli/main.py" in out
    assert "architecture map" in out.lower()


def test_arch_context_caps_long_file(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("x" * 9000)
    out = sc.arch_context(tmp_path, cap=1000)
    assert "truncated" in out
    assert len(out) < 1500  # capped, not the full 9000


def test_arch_context_empty_file_is_noop(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("   \n")
    assert sc.arch_context(tmp_path) == ""
