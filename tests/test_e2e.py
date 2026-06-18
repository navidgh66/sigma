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


# --------------------------- doctor + onboard E2E --------------------------- #
def test_onboard_then_doctor_clean(tmp_path, monkeypatch):
    """Onboard writes config + key; a follow-up doctor --check sees them healthy."""
    from cli import doctor, onboard, secrets

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Run onboard with everything injected — choose nlp, store one key, skip rtk.
    onboard.run_onboard(
        name="e2e",
        domain_input=lambda: "3",
        secret_input=lambda key: "gkey" if key == "GEMINI_API_KEY" else "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        spawn=lambda argv: 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["classic-ml", "deep-learning", "nlp", "rl"],
    )

    # Secret landed in ~/.sigma/.env, not the committed config.
    assert secrets.read_env().get("GEMINI_API_KEY") == "gkey"
    assert "gkey" not in (tmp_path / "sigma.config.yml").read_text()

    # doctor --check honours statuses: config OK + secrets WARN → exit 0
    # (warnings never fail the gate; only FAILs do). Full probe set is covered
    # in test_checks — here we assert the doctor wiring.
    from cli.checks import OK, WARN, Check

    rc = doctor.run_doctor(
        check_only=True,
        run_all=lambda: [Check("config", OK, "valid"), Check("secrets", WARN, "partial")],
        use_rich=False,
    )
    assert rc == 0
