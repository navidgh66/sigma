"""Tests for cli.claude_local — upsert a sigma-managed block into CLAUDE.local.md.

CLAUDE.local.md is gitignored and auto-loaded into every Claude Code session, so
it's the static fallback (alongside the SessionStart hook) for surfacing the learn
pointer. The block is delimited by markers so re-running `sigma learn` replaces it
idempotently without disturbing the user's own content.
"""

from __future__ import annotations

from cli import claude_local as cl


# --------------------------- pure upsert --------------------------- #
def test_upsert_inserts_when_absent():
    out = cl.upsert_block("", "POINTER")
    assert cl.START_MARKER in out
    assert cl.END_MARKER in out
    assert "POINTER" in out


def test_upsert_preserves_user_content():
    existing = "# My notes\n\nimportant stuff\n"
    out = cl.upsert_block(existing, "POINTER")
    assert "# My notes" in out
    assert "important stuff" in out
    assert "POINTER" in out


def test_upsert_replaces_between_markers():
    first = cl.upsert_block("# notes\n", "OLD POINTER")
    second = cl.upsert_block(first, "NEW POINTER")
    assert "NEW POINTER" in second
    assert "OLD POINTER" not in second
    # exactly one managed block, not appended twice
    assert second.count(cl.START_MARKER) == 1
    assert second.count(cl.END_MARKER) == 1


def test_upsert_idempotent_same_content():
    once = cl.upsert_block("# notes\n", "POINTER")
    twice = cl.upsert_block(once, "POINTER")
    assert once == twice


# --------------------------- file writer --------------------------- #
def test_write_block_creates_file(tmp_path):
    ok = cl.write_block(tmp_path, "POINTER")
    assert ok is True
    f = tmp_path / "CLAUDE.local.md"
    assert f.exists()
    assert "POINTER" in f.read_text()


def test_write_block_updates_existing_file(tmp_path):
    f = tmp_path / "CLAUDE.local.md"
    f.write_text("# my local notes\n")
    cl.write_block(tmp_path, "POINTER")
    text = f.read_text()
    assert "# my local notes" in text
    assert "POINTER" in text


def test_write_block_ensures_gitignored(tmp_path):
    cl.write_block(tmp_path, "POINTER")
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    assert "CLAUDE.local.md" in gi.read_text()


def test_write_block_gitignore_not_duplicated(tmp_path):
    gi = tmp_path / ".gitignore"
    gi.write_text("CLAUDE.local.md\n")
    cl.write_block(tmp_path, "POINTER")
    assert gi.read_text().count("CLAUDE.local.md") == 1


def test_write_block_best_effort_on_bad_root(tmp_path):
    # Pathological: root is a file, not a dir → returns False, never raises.
    bad = tmp_path / "afile"
    bad.write_text("x")
    assert cl.write_block(bad, "POINTER") is False
