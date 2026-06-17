"""Tests for cli.skill_map — stage→skill mapping and prompt injection."""

from __future__ import annotations

from pathlib import Path

from cli import skill_map


def _make_vendor(tmp_path: Path) -> Path:
    """Build a minimal vendored-skills tree under tmp_path/skills/vendor."""
    vendor = tmp_path / "skills" / "vendor"
    sp = vendor / "superpowers"
    for slug, body in {
        "brainstorming": "# Brainstorm\nExplore intent.",
        "writing-plans": "# Plans\nDecompose into tasks.",
        "test-driven-development": "# TDD\nRED GREEN REFACTOR.",
        "systematic-debugging": "# Debug\nFind root cause.",
        "verification-before-completion": "# Verify\nCheck before done.",
    }.items():
        d = sp / slug
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {slug}\n---\n{body}\n")
    cv = vendor / "caveman"
    cv.mkdir(parents=True)
    (cv / "SKILL.md").write_text("---\nname: caveman\n---\n# Caveman\nCompress output.\n")
    return vendor


def test_skills_for_known_stage_returns_slugs():
    assert "brainstorming" in skill_map.skills_for_stage("propose")
    assert "brainstorming" in skill_map.skills_for_stage("blueprint")
    assert skill_map.skills_for_stage("spec") == ["writing-plans"]
    assert skill_map.skills_for_stage("implement-task") == ["test-driven-development"]


def test_verify_stage_maps_both_checkers():
    skills = skill_map.skills_for_stage("verify")
    assert "systematic-debugging" in skills
    assert "verification-before-completion" in skills


def test_unknown_stage_returns_empty():
    assert skill_map.skills_for_stage("nonexistent") == []


def test_skill_paths_resolve_existing_files(tmp_path):
    vendor = _make_vendor(tmp_path)
    paths = skill_map.skill_paths("propose", vendor)
    assert paths
    assert all(p.exists() for p in paths)
    assert paths[0].name == "SKILL.md"


def test_skill_paths_graceful_when_missing(tmp_path):
    vendor = tmp_path / "skills" / "vendor"  # does not exist
    assert skill_map.skill_paths("propose", vendor) == []


def test_inject_skill_prepends_body(tmp_path):
    vendor = _make_vendor(tmp_path)
    out = skill_map.inject_skill("ORIGINAL PROMPT", "spec", vendor)
    assert "ORIGINAL PROMPT" in out
    assert "Decompose into tasks." in out  # writing-plans body present


def test_inject_skill_no_skill_returns_prompt_unchanged(tmp_path):
    vendor = _make_vendor(tmp_path)
    out = skill_map.inject_skill("ORIGINAL", "research", vendor)
    assert out == "ORIGINAL"


def test_inject_skill_terse_adds_caveman(tmp_path):
    vendor = _make_vendor(tmp_path)
    out = skill_map.inject_skill("ORIGINAL", "spec", vendor, terse=True)
    assert "Compress output." in out  # caveman injected when terse


def test_inject_skill_terse_on_unmapped_stage_still_caveman(tmp_path):
    vendor = _make_vendor(tmp_path)
    out = skill_map.inject_skill("ORIGINAL", "research", vendor, terse=True)
    assert "Compress output." in out
    assert "ORIGINAL" in out
