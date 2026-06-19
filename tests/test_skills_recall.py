"""Tests for cli.skills_recall — read-side recall of ratcheted lessons."""

from __future__ import annotations

from cli.loop import ratchet_to_skills
from cli.skills_recall import recall_lessons, render_recall_block


def _skills(tmp_path):
    return tmp_path / "skills"


# --------------------------- selection by domain --------------------------- #
def test_recall_matches_domain(tmp_path):
    skills = _skills(tmp_path)
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "use BPE not whitespace", "nlp")
    ratchet_to_skills(skills, "verify failed: train agent", "clip rewards", "rl")

    recall = recall_lessons(skills, "nlp")

    assert len(recall.lessons) == 1
    assert recall.lessons[0].domain == "nlp"
    assert "BPE" in recall.lessons[0].lesson


def test_recall_excludes_other_domains(tmp_path):
    skills = _skills(tmp_path)
    ratchet_to_skills(skills, "verify failed: train agent", "clip rewards", "rl")
    recall = recall_lessons(skills, "nlp")
    assert recall.lessons == []


def test_recall_excludes_skills_without_domain(tmp_path):
    skills = _skills(tmp_path)
    # A vendor-style skill with no domain frontmatter must never be recalled.
    d = skills / "some-vendor-skill"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: x\n---\n# X\nno domain here")
    recall = recall_lessons(skills, "nlp")
    assert recall.lessons == []


def test_recall_empty_when_no_domain_or_missing_dir(tmp_path):
    assert recall_lessons(tmp_path / "nope", "nlp").lessons == []
    assert recall_lessons(_skills(tmp_path), None).lessons == []


def test_recall_truncates_at_limit(tmp_path):
    skills = _skills(tmp_path)
    for i in range(5):
        ratchet_to_skills(skills, f"verify failed: task {i}", f"lesson {i}", "nlp")
    recall = recall_lessons(skills, "nlp", limit=3)
    assert len(recall.lessons) == 3
    assert recall.truncated is True


# --------------------------- rendering --------------------------- #
def test_render_includes_lesson_text(tmp_path):
    skills = _skills(tmp_path)
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "use BPE not whitespace", "nlp")
    block = render_recall_block(recall_lessons(skills, "nlp"))
    assert "past lessons" in block
    assert "use BPE not whitespace" in block
    assert "end past lessons" in block


def test_render_empty_recall_is_blank(tmp_path):
    block = render_recall_block(recall_lessons(_skills(tmp_path), "nlp"))
    assert block == ""


def test_render_marks_truncation(tmp_path):
    skills = _skills(tmp_path)
    for i in range(4):
        ratchet_to_skills(skills, f"verify failed: task {i}", f"lesson {i}", "nlp")
    block = render_recall_block(recall_lessons(skills, "nlp", limit=2))
    assert "older lessons omitted" in block
