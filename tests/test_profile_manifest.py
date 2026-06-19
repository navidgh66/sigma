"""Tests for cli/profile_manifest — skeleton contract + validation + staleness."""

from __future__ import annotations

import os

from cli.profile_manifest import (
    ML_LOGIC_HEADER,
    SYSTEM_LOGIC_HEADER,
    profile_path,
    profile_skeleton,
    staleness,
    validate_profile,
)


def test_skeleton_has_both_sections():
    text = profile_skeleton("demo")
    assert ML_LOGIC_HEADER in text
    assert SYSTEM_LOGIC_HEADER in text
    assert "demo" in text


def test_validate_skeleton_flags_empty_sections():
    # The skeleton's sections hold only comments → flagged empty.
    problems = validate_profile(profile_skeleton("demo"))
    assert any("ML-logic section is empty" in p for p in problems)
    assert any("system-logic section is empty" in p for p in problems)


def test_validate_missing_section():
    text = f"{ML_LOGIC_HEADER}\n\nsplit is grouped by user_id (features.py)\n"
    problems = validate_profile(text)
    assert any(SYSTEM_LOGIC_HEADER in p for p in problems)


def test_validate_well_formed_profile():
    text = "\n".join([
        ML_LOGIC_HEADER, "", "- split grouped by user_id (features.py)", "",
        SYSTEM_LOGIC_HEADER, "", "- queue consumer must be idempotent (worker.py)", "",
    ])
    assert validate_profile(text) == []


def test_profile_path_layout(tmp_path):
    p = profile_path(tmp_path)
    assert p == tmp_path / "sigma" / "profile" / "logic-profile.md"


def test_staleness_missing_profile(tmp_path):
    result = staleness(tmp_path / "nope.md", [tmp_path])
    assert not result.profile_exists
    assert not result.stale
    assert "no logic profile" in result.banner()


def test_staleness_fresh_profile(tmp_path):
    prof = tmp_path / "logic-profile.md"
    f = tmp_path / "model.py"
    f.write_text("x = 1\n")
    # Make the profile newer than the touched file.
    prof.write_text("# profile\n")
    old = f.stat().st_mtime - 100
    os.utime(f, (old, old))
    result = staleness(prof, [f])
    assert result.profile_exists
    assert not result.stale
    assert result.banner() == ""


def test_staleness_detects_newer_file(tmp_path):
    prof = tmp_path / "logic-profile.md"
    prof.write_text("# profile\n")
    f = tmp_path / "model.py"
    f.write_text("x = 1\n")
    # Make the touched file newer than the profile.
    newer = prof.stat().st_mtime + 100
    os.utime(f, (newer, newer))
    result = staleness(prof, [f])
    assert result.stale
    assert "OLDER" in result.banner()
    assert "model.py" in result.banner()


def test_staleness_skips_missing_touched_file(tmp_path):
    prof = tmp_path / "logic-profile.md"
    prof.write_text("# profile\n")
    result = staleness(prof, [tmp_path / "deleted.py"])
    assert not result.stale
