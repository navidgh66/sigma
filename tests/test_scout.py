"""Tests for cli.scout — pure relevance/rank/dedup/parse logic (no network)."""

from __future__ import annotations

from cli.scout import (
    SkillHit,
    dedup_against_bundle,
    domain_queries,
    parse_search_response,
    rank,
    score_relevance,
)


# --------------------------- domain queries --------------------------- #
def test_domain_queries_maps_known_skips_unknown():
    out = domain_queries(["nlp", "not-a-domain", "mlops"])
    domains = [d for d, _, _ in out]
    assert domains == ["nlp", "mlops"]
    # each carries a query + a category slug
    assert all(q and c for _, q, c in out)


# --------------------------- scoring --------------------------- #
def test_score_rewards_domain_keyword_overlap():
    relevant = SkillHit("RAG Helper", "llm prompt rag evaluation toolkit", "a/b")
    noise = SkillHit("Todo App", "a simple todo list", "c/d")
    assert score_relevance(relevant, ["llm-engineering"]) > score_relevance(noise, ["llm-engineering"])


def test_score_star_bump_cannot_beat_relevance():
    # A wildly popular but irrelevant skill must not outrank a relevant one.
    popular_noise = SkillHit("Star Repo", "unrelated web framework", "a/b", stars=100000)
    relevant = SkillHit("PyTorch Trainer", "deep learning pytorch neural network", "c/d", stars=5)
    s_noise = score_relevance(popular_noise, ["deep-learning"])
    s_rel = score_relevance(relevant, ["deep-learning"])
    assert s_rel > s_noise


# --------------------------- ranking --------------------------- #
def test_rank_is_deterministic_and_capped():
    hits = [
        SkillHit("A", "", "a/a", stars=1, score=1.0),
        SkillHit("B", "", "b/b", stars=9, score=3.0),
        SkillHit("C", "", "c/c", stars=5, score=3.0),  # tie with B on score → stars break
    ]
    out = rank(hits, limit=2)
    assert [h.name for h in out] == ["B", "C"]  # B before C (more stars), capped to 2


# --------------------------- dedup --------------------------- #
def test_dedup_drops_already_vendored(tmp_path):
    skills = tmp_path / "skills"
    (skills / "vendor" / "caveman").mkdir(parents=True)
    hits = [
        SkillHit("caveman", "x", "JuliusBrussee/caveman"),  # dir name match
        SkillHit("Fresh Skill", "y", "someone/fresh"),
    ]
    out = dedup_against_bundle(hits, skills)
    assert [h.name for h in out] == ["Fresh Skill"]


def test_dedup_matches_recorded_source(tmp_path):
    skills = tmp_path / "skills"
    d = skills / "sigma-cost"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: sigma-cost\nsource: github.com/acme/cost-skill\n---\n")
    hits = [
        SkillHit("Cost Skill", "x", "https://github.com/acme/cost-skill.git"),  # source match
        SkillHit("Other", "y", "acme/other"),
    ]
    out = dedup_against_bundle(hits, skills)
    assert [h.name for h in out] == ["Other"]


def test_dedup_no_bundle_dir_returns_all(tmp_path):
    hits = [SkillHit("A", "x", "a/a")]
    assert dedup_against_bundle(hits, tmp_path / "missing") == hits


# --------------------------- response parsing --------------------------- #
def test_parse_response_scores_and_skips_incomplete():
    payload = {
        "data": {
            "skills": [
                {"name": "RAG", "description": "llm rag eval", "githubUrl": "a/b", "stars": 10},
                {"name": "No Repo", "description": "missing url"},  # skipped (no githubUrl)
                {"description": "no name", "githubUrl": "c/d"},      # skipped (no name)
                "garbage",                                            # skipped (not a dict)
            ]
        }
    }
    hits = parse_search_response(payload, ["llm-engineering"])
    assert [h.name for h in hits] == ["RAG"]
    assert hits[0].score > 0  # scored against the domain


def test_parse_response_bad_shape_is_safe():
    assert parse_search_response({}, ["nlp"]) == []
    assert parse_search_response({"data": {}}, ["nlp"]) == []
    assert parse_search_response("nope", ["nlp"]) == []
