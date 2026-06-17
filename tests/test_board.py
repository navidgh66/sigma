"""Tests for cli.board — kanban projection over tasks + events."""

from __future__ import annotations

from pathlib import Path

from cli import board, events


def _ws(tmp_path: Path, tasks_md=None) -> Path:
    ws = tmp_path / "spec"
    ws.mkdir()
    if tasks_md is not None:
        (ws / "tasks.md").write_text(tasks_md)
    return ws


TASKS = """# Tasks

- [ ] T1 (nlp): tokenize corpus
- [x] T2 (mlops): register model
- [ ] T3 (rl): eval policy
"""


def test_build_columns_defaults_to_status_view(tmp_path):
    ws = _ws(tmp_path, TASKS)
    cols = board.build_columns(ws)
    names = [c.name for c in cols]
    assert "To Do" in names
    assert "Done" in names


def test_done_task_lands_in_done_column(tmp_path):
    ws = _ws(tmp_path, TASKS)
    cols = {c.name: c for c in board.build_columns(ws)}
    done_titles = [card.title for card in cols["Done"].cards]
    assert any("register model" in t for t in done_titles)


def test_incomplete_task_in_todo_when_no_events(tmp_path):
    ws = _ws(tmp_path, TASKS)
    cols = {c.name: c for c in board.build_columns(ws)}
    todo_titles = [card.title for card in cols["To Do"].cards]
    assert any("tokenize corpus" in t for t in todo_titles)


def test_event_moves_task_to_in_progress(tmp_path):
    ws = _ws(tmp_path, TASKS)
    events.append_event(ws, events.Event(task="T1", stage="implement-task", status="in_progress"))
    cols = {c.name: c for c in board.build_columns(ws)}
    wip_titles = [card.title for card in cols["In Progress"].cards]
    assert any("tokenize corpus" in t for t in wip_titles)


def test_event_failed_moves_task_to_blocked(tmp_path):
    ws = _ws(tmp_path, TASKS)
    events.append_event(ws, events.Event(task="T3", stage="verify", status="failed"))
    cols = {c.name: c for c in board.build_columns(ws)}
    blocked = [card.title for card in cols["Blocked"].cards]
    assert any("eval policy" in t for t in blocked)


def test_build_board_returns_renderable(tmp_path):
    ws = _ws(tmp_path, TASKS)
    layout = board.build_board(ws)
    # Must be a Rich renderable (has __rich_console__ or is a Layout/Table/etc.)
    assert layout is not None
    assert hasattr(layout, "__rich_console__") or hasattr(layout, "__rich__")


def test_build_board_empty_workspace(tmp_path):
    ws = _ws(tmp_path)  # no tasks.md
    layout = board.build_board(ws)
    assert layout is not None


def test_render_static_smoke(tmp_path, capsys):
    ws = _ws(tmp_path, TASKS)
    board.render_static(ws)
    out = capsys.readouterr().out
    assert "tokenize corpus" in out or "T1" in out


def test_card_counts_in_columns(tmp_path):
    ws = _ws(tmp_path, TASKS)
    cols = {c.name: c for c in board.build_columns(ws)}
    total = sum(len(c.cards) for c in cols.values())
    assert total == 3  # all three tasks placed exactly once
