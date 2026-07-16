"""Tests for cli.claude_md_ref — confirm-gated ARCHITECTURE.md reference in CLAUDE.md.

Unlike CLAUDE.local.md (gitignored, always refreshed), CLAUDE.md is committed
and shared, so writing to it requires explicit confirmation — mirrors the
RTK/caveman/statusline confirm-gate shape.
"""

from __future__ import annotations

from cli import claude_md_ref as ref


# --------------------------- pure upsert --------------------------- #
def test_upsert_inserts_when_absent():
    out = ref.upsert_reference("# CLAUDE.md\n\nSome content.\n")
    assert ref.START_MARKER in out
    assert ref.END_MARKER in out
    assert "ARCHITECTURE.md" in out


def test_upsert_preserves_existing_content():
    existing = "# CLAUDE.md\n\n## What this is\n\nSome project.\n"
    out = ref.upsert_reference(existing)
    assert "## What this is" in out
    assert "Some project." in out


def test_upsert_replaces_between_markers_idempotent():
    once = ref.upsert_reference("# CLAUDE.md\n")
    twice = ref.upsert_reference(once)
    assert once == twice
    assert once.count(ref.START_MARKER) == 1
    assert once.count(ref.END_MARKER) == 1


def test_has_reference_false_when_absent():
    assert ref.has_reference("# CLAUDE.md\n\nNo pointer here.\n") is False


def test_has_reference_true_after_upsert():
    out = ref.upsert_reference("# CLAUDE.md\n")
    assert ref.has_reference(out) is True


# --------------------------- file writer --------------------------- #
def test_write_reference_updates_file(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("# my project\n")
    assert ref.write_reference(tmp_path) is True
    text = f.read_text()
    assert "# my project" in text
    assert "ARCHITECTURE.md" in text


def test_write_reference_best_effort_on_bad_root(tmp_path):
    bad = tmp_path / "notadir"
    bad.write_text("x")
    assert ref.write_reference(bad) is False


# --------------------------- confirm-gated setup --------------------------- #
def test_setup_noop_when_no_claude_md(tmp_path):
    calls = []
    assert ref.setup_claude_md_reference(tmp_path, confirm=lambda m: calls.append(m) or True) is False
    assert calls == []
    assert not (tmp_path / "CLAUDE.md").exists()


def test_setup_noop_when_already_present(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text(ref.upsert_reference("# CLAUDE.md\n"))
    calls = []
    assert ref.setup_claude_md_reference(tmp_path, confirm=lambda m: calls.append(m) or True) is False
    assert calls == []


def test_setup_asks_before_writing(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nProject notes.\n")
    calls = []

    def confirm(msg):
        calls.append(msg)
        return True

    assert ref.setup_claude_md_reference(tmp_path, confirm=confirm) is True
    assert len(calls) == 1
    assert "CLAUDE.md" in calls[0]
    assert "ARCHITECTURE.md" in f.read_text()


def test_setup_declines_without_confirm(tmp_path):
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nProject notes.\n")

    assert ref.setup_claude_md_reference(tmp_path, confirm=lambda m: False) is False
    assert "ARCHITECTURE.md" not in f.read_text()


def test_setup_default_confirm_declines(tmp_path):
    # No confirm fn given → defaults to always-deny, like setup_statusline/setup_rtk.
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n")
    assert ref.setup_claude_md_reference(tmp_path) is False
