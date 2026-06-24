"""Tests for cli.scout_run — discovery + install orchestration with fakes.

No network, no git, no real filesystem outside tmp: fetch and clone are injected.
"""

from __future__ import annotations

from cli.scout import SkillHit
from cli.scout_run import discover, install_hits, search_url


def _payload(*names):
    return {
        "data": {
            "skills": [
                {"name": n, "description": "llm rag evaluation toolkit",
                 "githubUrl": f"owner/{n}", "stars": 10}
                for n in names
            ]
        }
    }


# --------------------------- search url --------------------------- #
def test_search_url_encodes_query_and_sort():
    url = search_url("llm rag", category="data-ai", recent=True)
    assert "q=llm+rag" in url
    assert "category=data-ai" in url
    assert "sortBy=recent" in url


def test_search_url_defaults_to_stars():
    assert "sortBy=stars" in search_url("x")


# --------------------------- discover --------------------------- #
def test_discover_aggregates_and_ranks():
    def fetch(url, api_key):
        return _payload("rag-helper", "eval-kit")

    res = discover(["llm-engineering"], fetch=fetch, skills_dir=None)
    assert res.ok
    names = {h.name for h in res.hits}
    assert names == {"rag-helper", "eval-kit"}


def test_discover_dedups_same_skill_across_queries():
    # Two domains, the SAME skill returned for both → surfaced once.
    def fetch(url, api_key):
        return _payload("shared-skill")

    res = discover(["nlp", "llm-engineering"], fetch=fetch, skills_dir=None)
    assert res.ok
    assert len(res.hits) == 1


def test_discover_failsafe_when_api_down():
    def fetch(url, api_key):
        return None  # every request fails

    res = discover(["nlp"], fetch=fetch, skills_dir=None)
    assert res.ok is False
    assert "unreachable" in res.note or "rate-limited" in res.note
    assert res.hits == []


def test_discover_partial_success_still_ranks():
    calls = {"n": 0}

    def fetch(url, api_key):
        calls["n"] += 1
        # first query fails, second returns
        return None if calls["n"] == 1 else _payload("late-skill")

    res = discover(["nlp", "llm-engineering"], fetch=fetch, skills_dir=None)
    assert res.ok
    assert [h.name for h in res.hits] == ["late-skill"]


def test_discover_no_known_domains():
    res = discover(["totally-unknown"], fetch=lambda u, k: _payload("x"), skills_dir=None)
    assert res.ok is False
    assert "no known" in res.note


def test_discover_dedups_against_bundle(tmp_path):
    skills = tmp_path / "skills"
    (skills / "owner-rag").mkdir(parents=True)  # NOTE: dir name won't match key

    def fetch(url, api_key):
        return _payload("rag")

    # Seed a dir whose name equals the hit's slug so dedup drops it.
    (skills / "rag").mkdir(parents=True)
    res = discover(["llm-engineering"], fetch=fetch, skills_dir=skills)
    assert res.ok
    assert res.hits == []  # the only hit was already in the bundle
    assert "already in the bundle" in res.note


# --------------------------- install --------------------------- #
def test_install_only_confirmed_hits(tmp_path):
    hits = [
        SkillHit("yes-skill", "x", "owner/yes"),
        SkillHit("no-skill", "y", "owner/no"),
    ]
    cloned = []

    def clone(url, dest):
        cloned.append(url)
        return True

    installed = install_hits(
        hits, tmp_path, confirm=lambda h: h.name == "yes-skill", clone=clone
    )
    assert cloned == ["owner/yes"]
    assert len(installed) == 1


def test_install_skips_on_clone_failure(tmp_path):
    hits = [SkillHit("s", "x", "owner/s")]
    installed = install_hits(hits, tmp_path, confirm=lambda h: True, clone=lambda u, d: False)
    assert installed == []  # clone failed → not counted
