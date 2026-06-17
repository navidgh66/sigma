"""Kanban board: a pure projection over tasks.md + events.jsonl, rendered with Rich.

`build_columns` folds the parsed tasks and the latest event per task into status
columns (To Do / In Progress / Blocked / Done) — pure and testable. `build_board`
wraps the columns into a Rich Layout. `render_static` prints once; `render_live`
redraws on an interval as agents emit events. The board never mutates state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli import events
from cli.loop import parse_tasks

# Status columns, in display order. Maps event status → column.
TODO = "To Do"
IN_PROGRESS = "In Progress"
BLOCKED = "Blocked"
DONE = "Done"
COLUMN_ORDER = [TODO, IN_PROGRESS, BLOCKED, DONE]

_STATUS_TO_COLUMN = {
    events.STATUS_PENDING: TODO,
    events.STATUS_IN_PROGRESS: IN_PROGRESS,
    events.STATUS_BLOCKED: BLOCKED,
    events.STATUS_FAILED: BLOCKED,
    events.STATUS_DONE: DONE,
}

_COLUMN_STYLE = {
    TODO: "white",
    IN_PROGRESS: "yellow",
    BLOCKED: "red",
    DONE: "green",
}


@dataclass
class Card:
    task_id: Optional[str]
    title: str
    domain: Optional[str]
    status: str


@dataclass
class Column:
    name: str
    cards: List[Card] = field(default_factory=list)


def _task_key(task) -> str:
    """Stable key to match a task line to its events (prefer id, else title)."""
    return task.id or task.title


def build_columns(workspace: Path) -> List[Column]:
    """Project tasks + latest events into ordered status columns."""
    tasks_file = workspace / "tasks.md"
    tasks = parse_tasks(tasks_file.read_text()) if tasks_file.exists() else []
    latest = events.latest_by_task(events.read_events(workspace))

    columns: Dict[str, Column] = {name: Column(name=name) for name in COLUMN_ORDER}

    for task in tasks:
        key = _task_key(task)
        ev = latest.get(key)
        if ev is not None:
            col_name = _STATUS_TO_COLUMN.get(ev.status, TODO)
            status = ev.status
        elif task.done:
            col_name = DONE
            status = events.STATUS_DONE
        else:
            col_name = TODO
            status = events.STATUS_PENDING
        # A checklist-completed task always counts as Done even without an event.
        if task.done and ev is None:
            col_name = DONE
        columns[col_name].cards.append(
            Card(task_id=task.id, title=task.title, domain=task.domain, status=status)
        )

    return [columns[name] for name in COLUMN_ORDER]


def _render_column(column: Column) -> Panel:
    table = Table.grid(padding=(0, 0))
    if not column.cards:
        table.add_row(Text("—", style="dim"))
    for card in column.cards:
        label = card.task_id or ""
        domain = f" ({card.domain})" if card.domain else ""
        line = Text()
        if label:
            line.append(f"{label} ", style="bold")
        line.append(card.title)
        if domain:
            line.append(domain, style="dim cyan")
        table.add_row(line)
    style = _COLUMN_STYLE.get(column.name, "white")
    return Panel(
        table,
        title=f"[bold]{column.name}[/] ({len(column.cards)})",
        border_style=style,
    )


def build_board(workspace: Path) -> Layout:
    """Build a Rich Layout: one panel per status column, side by side."""
    columns = build_columns(workspace)
    layout = Layout()
    layout.split_row(*[Layout(_render_column(c), name=c.name) for c in columns])
    return layout


def render_static(workspace: Path, console: Optional[Console] = None) -> None:
    """Print the board once and return."""
    console = console or Console()
    console.print(build_board(workspace))


def render_live(
    workspace: Path,
    fps: int = 2,
    iterations: Optional[int] = None,
    console: Optional[Console] = None,
) -> None:
    """Redraw the board on an interval as events arrive.

    `iterations` bounds the loop for tests; None runs until interrupted.
    """
    from rich.live import Live

    console = console or Console()
    interval = 1.0 / max(fps, 1)
    count = 0
    with Live(build_board(workspace), console=console, refresh_per_second=fps) as live:
        try:
            while iterations is None or count < iterations:
                time.sleep(interval)
                live.update(build_board(workspace))
                count += 1
        except KeyboardInterrupt:
            pass
