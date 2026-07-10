"""Tests for cli.claude_md_scaffold — pure logic for generating a best-practice-
shaped CLAUDE.md / CLAUDE.local.md starter (distinct from Claude Code's native
/init, which has no length/structure discipline).
"""

from __future__ import annotations

from cli import claude_md_scaffold as s


def test_build_prompt_for_repo_target_mentions_shared_conventions():
    prompt = s.build_scaffold_prompt(root="/repo", target="repo")
    assert "CLAUDE.md" in prompt
    assert "team" in prompt.lower() or "shared" in prompt.lower()


def test_build_prompt_for_local_target_mentions_personal():
    prompt = s.build_scaffold_prompt(root="/repo", target="local")
    assert "CLAUDE.local.md" in prompt
    assert "personal" in prompt.lower()


def test_build_prompt_rejects_unknown_target():
    import pytest

    with pytest.raises(ValueError):
        s.build_scaffold_prompt(root="/repo", target="global")


def test_build_prompt_enforces_length_cap():
    prompt = s.build_scaffold_prompt(root="/repo", target="repo")
    assert "200" in prompt or "line" in prompt.lower()


def test_filename_for_target_repo():
    assert s.filename_for("repo") == "CLAUDE.md"


def test_filename_for_target_local():
    assert s.filename_for("local") == "CLAUDE.local.md"


def test_filename_for_unknown_target_raises():
    import pytest

    with pytest.raises(ValueError):
        s.filename_for("global")


def test_skeleton_has_what_why_how_sections():
    text = s.skeleton("myproject", target="repo")
    assert "WHAT" in text or "What" in text
    assert "WHY" in text or "Why" in text
    assert "HOW" in text or "How" in text


def test_skeleton_under_length_cap():
    text = s.skeleton("myproject", target="repo")
    assert len(text.splitlines()) < 200
