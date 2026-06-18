"""Tests for cli.weave_manifest — pure manifest builder + HTML validator."""

from __future__ import annotations

from cli.weave_manifest import (
    build_manifest,
    present_file_stages,
    validate_chain_html,
)


def _workspace(tmp_path, **files):
    ws = tmp_path / "ws"
    ws.mkdir()
    for name, content in files.items():
        (ws / name).write_text(content)
    return ws


# --------------------------- build_manifest --------------------------- #
def test_manifest_counts_citations_and_headings(tmp_path):
    # Arrange
    research = "# Summary\nA claim [1] and a [link](http://x).\n## Findings\nmore"
    ws = _workspace(tmp_path, **{"research.md": research})

    # Act
    manifest = build_manifest(ws, topic="auth", slug="2026-06-18-auth")

    # Assert
    research_entry = next(s for s in manifest["stages"] if s["name"] == "research")
    assert research_entry["exists"] is True
    assert research_entry["citations"] == 2
    assert research_entry["headings"] == ["Summary", "Findings"]
    assert research_entry["bytes"] == len(research.encode("utf-8"))


def test_manifest_marks_missing_and_incomplete(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R"})
    manifest = build_manifest(ws)
    assert manifest["chain_complete"] is False
    assert "spec" in manifest["missing"]
    assert "research" not in manifest["missing"]


def test_manifest_directory_artifact(tmp_path):
    ws = _workspace(tmp_path)
    impl = ws / "impl"
    impl.mkdir()
    (impl / "a.md").write_text("x")
    (impl / "b.md").write_text("y")

    manifest = build_manifest(ws)
    impl_entry = next(s for s in manifest["stages"] if s["name"] == "implement-task")
    assert impl_entry["is_dir"] is True
    assert impl_entry["exists"] is True
    assert impl_entry["files"] == 2


def test_manifest_is_deterministic_no_timestamp(tmp_path):
    ws = _workspace(tmp_path, **{"spec.md": "# Spec"})
    first = build_manifest(ws, topic="t", slug="s")
    second = build_manifest(ws, topic="t", slug="s")
    assert first == second
    # No generated timestamp key leaked into the pure manifest.
    assert "ts" not in first
    assert "generated_at" not in first


def test_present_file_stages_excludes_dirs_and_missing(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R", "spec.md": "# S"})
    (ws / "impl").mkdir()
    manifest = build_manifest(ws)
    names = [s["name"] for s in present_file_stages(manifest)]
    assert "research" in names
    assert "spec" in names
    assert "implement-task" not in names  # directory
    assert "tasks" not in names  # missing


# --------------------------- validate_chain_html --------------------------- #
def test_validate_html_passes_well_formed():
    html = "<!DOCTYPE html><html><body><h1>research</h1><h2>spec</h2></body></html>"
    problems = validate_chain_html(html, ["research", "spec"])
    assert problems == []


def test_validate_html_flags_missing_stage_section():
    html = "<!DOCTYPE html><html><body><h1>research</h1></body></html>"
    problems = validate_chain_html(html, ["research", "spec"])
    assert any("spec" in p for p in problems)


def test_validate_html_flags_malformed():
    problems = validate_chain_html("just text", ["research"])
    assert any("<html>" in p for p in problems)


def test_validate_html_empty():
    assert validate_chain_html("", ["research"]) == ["chain.html is empty"]
