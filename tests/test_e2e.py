"""End-to-end: the full Hermes → pipeline → events → board flow with fake agents.

Proves the pieces wire together: Hermes routes by workspace state, runs stages
through the real execute_stage (with an injected runner so no real claude is
spawned), emits events, and the board projects those events into columns.
"""

from __future__ import annotations

from pathlib import Path

from cli import board, events, hermes
from cli.runner import AgentResult


class FakeRunner:
    """A runner that always succeeds, returning canned stage output."""

    def run(self, prompt, cwd=None):
        # A verify prompt should pass; everything else returns generic output.
        if "VERDICT" in prompt:
            return AgentResult(ok=True, output="checks pass\nVERDICT: PASS")
        return AgentResult(ok=True, output="# stage output\nbody")


def _seed_commands(tmp_home: Path) -> None:
    """Create minimal command templates so execute_stage finds them."""
    cmds = tmp_home / "commands"
    cmds.mkdir(parents=True)
    for name in ("research", "propose", "blueprint", "spec"):
        (cmds / f"{name}.md").write_text(f"# /{name}\nDo the {name} stage.")


def test_hermes_single_step_then_board(tmp_path, monkeypatch):
    # Arrange: a sigma install (templates) + a project workspace.
    home = tmp_path / "home"
    _seed_commands(home)
    monkeypatch.setenv("SIGMA_HOME", str(home))

    ws = tmp_path / "specs" / "2026-06-17-demo"
    ws.mkdir(parents=True)
    (ws / "research.md").write_text("# Research\nfindings")  # next stage = propose

    # Act: one Hermes hop (state-driven → propose), real execute_stage + fake agent.
    result = hermes.run_hermes(
        "continue",
        ws,
        make_runner=lambda: FakeRunner(),
        now="2026-06-17T12:00:00",
    )

    # Assert: propose ran, artifact written, events + log emitted.
    assert result.ok
    assert result.stages_run == ["propose"]
    assert (ws / "proposals.md").exists()
    assert (ws / "hermes-log.md").exists()
    evs = events.read_events(ws)
    assert any(e.stage == "propose" and e.status == "done" for e in evs)

    # And the board builds cleanly (tasks.md absent → no cards, but valid layout).
    assert board.build_columns(ws) is not None
    assert board.build_board(ws) is not None


def test_hermes_auto_chain_stops_at_spec_gate(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _seed_commands(home)
    monkeypatch.setenv("SIGMA_HOME", str(home))

    ws = tmp_path / "specs" / "2026-06-17-auto"
    ws.mkdir(parents=True)  # empty → chain from research

    result = hermes.run_hermes(
        "build the whole thing",
        ws,
        auto=True,
        make_runner=lambda: FakeRunner(),
        now="2026-06-17T12:00:00",
    )

    assert result.stages_run == ["research", "propose", "blueprint", "spec"]
    assert result.gate == "spec-approval"
    for artifact in ("research.md", "proposals.md", "architecture.md", "spec.md"):
        assert (ws / artifact).exists()
