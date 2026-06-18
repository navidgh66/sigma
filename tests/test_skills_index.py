"""Tests for cli.skills_index — topic-key normalization + contradiction detection."""

from __future__ import annotations

from cli import skills_index


# --------------------------- topic_key --------------------------- #
def test_topic_key_normalizes():
    assert skills_index.topic_key("Tokenize Corpus") == "tokenize-corpus"


def test_topic_key_strips_ratchet_noise():
    # "verify failed:" / "implement failed:" prefixes are noise, not topic.
    a = skills_index.topic_key("verify failed: tokenize corpus")
    b = skills_index.topic_key("implement failed: tokenize corpus")
    assert a == b == "tokenize-corpus"


def test_topic_key_stable_on_punctuation():
    assert skills_index.topic_key("Eval  policy!!") == skills_index.topic_key("eval policy")


# --------------------------- find_contradictions --------------------------- #
def _write_skill(skills_dir, slug, title, domain):
    from cli.loop import render_skill

    d = skills_dir / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(render_skill(title, "some lesson", domain))


def test_no_contradiction_in_empty_dir(tmp_path):
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert found == []


def test_detects_same_domain_same_topic(tmp_path):
    _write_skill(tmp_path, "old", "verify failed: tokenize corpus", "nlp")
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert len(found) == 1
    assert found[0].name == "SKILL.md"


def test_no_match_different_domain(tmp_path):
    _write_skill(tmp_path, "old", "verify failed: tokenize corpus", "rl")
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert found == []


def test_no_match_different_topic(tmp_path):
    _write_skill(tmp_path, "old", "verify failed: train classifier", "nlp")
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert found == []


def test_detects_multiple_candidates(tmp_path):
    _write_skill(tmp_path, "old1", "verify failed: tokenize corpus", "nlp")
    _write_skill(tmp_path, "old2", "implement failed: tokenize corpus", "nlp")
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert len(found) == 2


def test_skips_skill_without_domain(tmp_path):
    _write_skill(tmp_path, "nodomain", "verify failed: tokenize corpus", None)
    found = skills_index.find_contradictions(tmp_path, "nlp", "tokenize-corpus")
    assert found == []  # no domain in frontmatter → not a same-domain match


def test_parse_skill_meta(tmp_path):
    _write_skill(tmp_path, "s", "verify failed: eval policy", "rl")
    meta = skills_index.parse_skill_meta(tmp_path / "s" / "SKILL.md")
    assert meta["domain"] == "rl"
    assert meta["topic"] == "eval-policy"
