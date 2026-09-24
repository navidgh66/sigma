"""Tests for cli.ratchet: lessons written into skills/ + contradiction flags."""

from cli.ratchet import ratchet_to_skills, render_skill
from cli.skills_index import parse_skill_meta


def test_render_skill_has_frontmatter():
    body = render_skill("tokenizer mismatch", "Always align tokenizer to model", domain="nlp")
    assert body.startswith("---")
    assert "name: tokenizer-mismatch" in body
    assert "  domain: nlp" in body
    assert "created:" not in body


def test_render_skill_with_created():
    body = render_skill("x", "y", domain="nlp", created="2026-09-24")
    assert "metadata:\n  domain: nlp\n  created: 2026-09-24" in body


def test_ratchet_writes_skill(tmp_path):
    out = ratchet_to_skills(tmp_path, "Off by one in returns", "Use t..T-1", domain="rl")
    assert out.name == "SKILL.md"
    assert "off-by-one-in-returns" in str(out.parent)


def test_ratchet_created_round_trips_through_meta(tmp_path):
    out = ratchet_to_skills(tmp_path, "leak", "split first", domain="classic-ml", created="2026-09-01")
    meta = parse_skill_meta(out)
    assert meta["domain"] == "classic-ml"
    assert meta["created"] == "2026-09-01"


def test_ratchet_flags_contradiction(tmp_path):
    skills = tmp_path / "skills"
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "lesson A", "nlp")
    out2 = ratchet_to_skills(skills, "verify failed: tokenize corpus", "lesson B", "nlp")
    assert "CONTRADICTION" in out2.read_text()
    assert (skills / "CONTRADICTIONS.md").exists()


def test_ratchet_no_contradiction_different_topic(tmp_path):
    skills = tmp_path / "skills"
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "A", "nlp")
    out2 = ratchet_to_skills(skills, "verify failed: train classifier", "B", "nlp")
    assert "CONTRADICTION" not in out2.read_text()
    assert not (skills / "CONTRADICTIONS.md").exists()


def test_ratchet_never_overwrites_an_earlier_lesson(tmp_path):
    skills = tmp_path / "skills"
    first = ratchet_to_skills(skills, "loop failed: tokenize corpus", "lesson A", "nlp")
    second = ratchet_to_skills(skills, "loop failed: tokenize corpus", "lesson B", "nlp")
    assert first != second
    assert "lesson A" in first.read_text()
    assert second.parent.name == "loop-failed-tokenize-corpus-2"
    assert "CONTRADICTION" in second.read_text() and str(first.parent.name) in second.read_text()
