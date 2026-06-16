
from cli.pipeline import (
    STAGE_NAMES,
    load_stage,
    next_stage,
    render_invocation,
)


def test_stage_order():
    assert STAGE_NAMES[0] == "research"
    assert STAGE_NAMES[-1] == "loop"
    assert "spec" in STAGE_NAMES


def test_next_stage():
    assert next_stage("research") == "propose"
    assert next_stage("spec") == "tasks"
    assert next_stage("loop") is None
    assert next_stage("unknown") is None


def test_load_stage_resolves_template():
    stage = load_stage("spec")
    assert stage is not None
    assert stage.name == "spec"
    # The real template ships in the repo, so it should exist.
    assert stage.exists is True


def test_load_stage_unknown():
    assert load_stage("nope") is None


def test_render_invocation_embeds_workspace(tmp_path):
    stage = load_stage("spec")
    ws = tmp_path / "ws"
    text = render_invocation(stage, ws)
    assert str(ws) in text
    assert "spec" in text
