from cli.lessons import (
    archive_lesson,
    efficacy,
    list_domain_lessons,
    render_report,
)
from cli.skills_recall import recall_lessons
from cli.trajectory import build_step


def _write_lesson(skills_dir, slug, domain="nlp"):
    d = skills_dir / slug
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: x\nmetadata:\n  domain: {domain}\n---\n\n# {slug}\n"
    )


def _cycle(ok, lessons, domain="nlp"):
    return build_step({"role": "cycle", "ok": ok, "domain": domain, "lessons": lessons})


def test_list_domain_lessons_excludes_archive_and_untagged(tmp_path):
    _write_lesson(tmp_path, "live-lesson")
    _write_lesson(tmp_path / "archive", "old-lesson")
    vendor = tmp_path / "vendor" / "thing"
    vendor.mkdir(parents=True)
    (vendor / "SKILL.md").write_text("---\nname: thing\n---\n# no domain\n")
    slugs = {le.slug for le in list_domain_lessons(tmp_path)}
    assert slugs == {"live-lesson"}


def test_efficacy_buckets_working_and_not_working(tmp_path):
    _write_lesson(tmp_path, "good-lesson")
    _write_lesson(tmp_path, "bad-lesson")
    steps = [
        _cycle(True, ["good-lesson"]),
        _cycle(True, ["good-lesson"]),
        _cycle(False, ["bad-lesson"]),
        _cycle(False, ["bad-lesson"]),
        _cycle(True, ["bad-lesson"]),  # 1/3 < 50%
    ]
    report = efficacy(steps, list_domain_lessons(tmp_path))
    assert [s.slug for s in report.working] == ["good-lesson"]
    assert [s.slug for s in report.not_working] == ["bad-lesson"]
    assert report.working[0].pass_rate == 1.0


def test_efficacy_no_evidence_bucket_and_absent_evidence_guard(tmp_path):
    _write_lesson(tmp_path, "idle-lesson")
    # Zero recall-carrying cycles → no evidence at all; report says so.
    report = efficacy([], list_domain_lessons(tmp_path))
    assert not report.has_recall_evidence
    assert "absent evidence" in render_report(report)
    # With evidence, the never-recalled lesson lands in no_evidence.
    report2 = efficacy([_cycle(True, ["other"])], list_domain_lessons(tmp_path))
    assert report2.has_recall_evidence
    assert [s.slug for s in report2.no_evidence] == ["idle-lesson"]


def test_archive_lesson_moves_and_is_excluded_from_recall(tmp_path):
    _write_lesson(tmp_path, "stale-lesson", domain="nlp")
    assert len(recall_lessons(tmp_path, "nlp").lessons) == 1
    dest = archive_lesson(tmp_path, "stale-lesson")
    assert dest is not None and dest.exists()
    assert not (tmp_path / "stale-lesson").exists()
    # Archived → out of recall entirely (the point of the move).
    assert recall_lessons(tmp_path, "nlp").lessons == []
    # And out of the live-lesson listing.
    assert list_domain_lessons(tmp_path) == []


def test_archive_lesson_never_overwrites(tmp_path):
    _write_lesson(tmp_path, "dup-lesson")
    _write_lesson(tmp_path / "archive", "dup-lesson")
    assert archive_lesson(tmp_path, "dup-lesson") is None
    assert (tmp_path / "dup-lesson").exists()  # untouched


def test_archive_missing_lesson_returns_none(tmp_path):
    assert archive_lesson(tmp_path, "ghost") is None
