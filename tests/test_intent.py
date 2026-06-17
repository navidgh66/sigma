"""Tests for cli.intent — hybrid routing (state-scan default + intent override)."""

from __future__ import annotations

from pathlib import Path

from cli import intent
from cli.runner import AgentResult


class FakeRunner:
    """Stand-in AgentRunner returning a scripted classification reply."""

    def __init__(self, reply: str, ok: bool = True):
        self._reply = reply
        self._ok = ok
        self.calls = 0

    def run(self, prompt, cwd=None):
        self.calls += 1
        return AgentResult(ok=self._ok, output=self._reply)


def _ws_with(tmp_path: Path, artifacts) -> Path:
    ws = tmp_path / "spec"
    ws.mkdir()
    for name in artifacts:
        (ws / name).write_text("x")
    return ws


# --------------------------- state scan --------------------------- #
def test_scan_empty_workspace_is_research(tmp_path):
    ws = _ws_with(tmp_path, [])
    assert intent.scan_state(ws) == "research"


def test_scan_after_research_is_propose(tmp_path):
    ws = _ws_with(tmp_path, ["research.md"])
    assert intent.scan_state(ws) == "propose"


def test_scan_after_spec_is_tasks(tmp_path):
    ws = _ws_with(tmp_path, ["research.md", "proposals.md", "architecture.md", "spec.md"])
    assert intent.scan_state(ws) == "tasks"


def test_scan_after_tasks_is_implement_task(tmp_path):
    ws = _ws_with(
        tmp_path,
        ["research.md", "proposals.md", "architecture.md", "spec.md", "tasks.md"],
    )
    assert intent.scan_state(ws) == "implement-task"


# --------------------------- override detection --------------------------- #
def test_needs_override_on_jump_signal():
    assert intent.needs_override("redo the research please")
    assert intent.needs_override("skip to verify")
    assert intent.needs_override("go back to spec")


def test_no_override_on_plain_continue():
    assert not intent.needs_override("looks good, continue")
    assert not intent.needs_override("")


# --------------------------- route --------------------------- #
def test_route_state_driven_no_model_call(tmp_path):
    ws = _ws_with(tmp_path, ["research.md"])
    runner = FakeRunner("verify")
    route = intent.route("continue", ws, runner)
    assert route.stage == "propose"
    assert runner.calls == 0  # state-driven, zero model cost
    assert "state" in route.reason.lower()


def test_route_override_calls_model(tmp_path):
    ws = _ws_with(tmp_path, ["research.md"])
    runner = FakeRunner("STAGE: verify\nDOMAIN: nlp")
    route = intent.route("skip to verify", ws, runner)
    assert route.stage == "verify"
    assert route.domain == "nlp"
    assert runner.calls == 1


def test_route_override_unparseable_falls_back_to_state(tmp_path):
    ws = _ws_with(tmp_path, ["research.md"])
    runner = FakeRunner("garbage with no stage line")
    route = intent.route("redo something weird", ws, runner)
    # Falls back to state-driven next stage when classification yields no stage.
    assert route.stage == "propose"


def test_route_override_runner_error_falls_back(tmp_path):
    ws = _ws_with(tmp_path, ["research.md"])
    runner = FakeRunner("", ok=False)
    route = intent.route("skip to verify", ws, runner)
    assert route.stage == "propose"  # state fallback


def test_classify_parses_stage_and_domain():
    runner = FakeRunner("STAGE: tasks\nDOMAIN: rl")
    route = intent.classify("anything", runner)
    assert route.stage == "tasks"
    assert route.domain == "rl"


def test_classify_rejects_invalid_stage():
    runner = FakeRunner("STAGE: bogus\nDOMAIN: rl")
    route = intent.classify("anything", runner)
    assert route.stage is None
