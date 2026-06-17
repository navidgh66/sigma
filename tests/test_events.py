"""Tests for cli.events — append-only board state spine (events.jsonl)."""

from __future__ import annotations

from cli import events


def test_append_then_read_roundtrip(tmp_path):
    events.append_event(tmp_path, events.Event(task="T1", stage="research", status="in_progress"))
    events.append_event(tmp_path, events.Event(task="T1", stage="research", status="done"))
    got = events.read_events(tmp_path)
    assert len(got) == 2
    assert got[0].task == "T1"
    assert got[0].status == "in_progress"
    assert got[1].status == "done"


def test_read_missing_file_returns_empty(tmp_path):
    assert events.read_events(tmp_path) == []


def test_append_creates_jsonl_file(tmp_path):
    events.append_event(tmp_path, events.Event(task="T2", stage="spec", status="done"))
    f = tmp_path / "events.jsonl"
    assert f.exists()
    assert f.read_text().count("\n") == 1  # one line per event


def test_event_optional_fields_default(tmp_path):
    events.append_event(tmp_path, events.Event(task="T3", stage="verify", status="done"))
    e = events.read_events(tmp_path)[0]
    assert e.agent is None
    assert e.verdict is None
    assert e.ts is None


def test_event_carries_ts_agent_verdict(tmp_path):
    events.append_event(
        tmp_path,
        events.Event(
            task="T4",
            stage="verify",
            status="done",
            agent="checker",
            verdict="PASS",
            ts="2026-06-17T12:00:00",
        ),
    )
    e = events.read_events(tmp_path)[0]
    assert e.agent == "checker"
    assert e.verdict == "PASS"
    assert e.ts == "2026-06-17T12:00:00"


def test_corrupt_line_is_skipped(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_text('{"task": "T1", "stage": "spec", "status": "done"}\nNOT JSON\n')
    got = events.read_events(tmp_path)
    assert len(got) == 1
    assert got[0].task == "T1"


def test_latest_by_task_keeps_last_status(tmp_path):
    events.append_event(tmp_path, events.Event(task="T1", stage="research", status="in_progress"))
    events.append_event(tmp_path, events.Event(task="T1", stage="research", status="done"))
    events.append_event(tmp_path, events.Event(task="T2", stage="spec", status="in_progress"))
    latest = events.latest_by_task(events.read_events(tmp_path))
    assert latest["T1"].status == "done"
    assert latest["T2"].status == "in_progress"
