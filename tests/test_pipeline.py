
import json

from cli.pipeline import (
    STAGE_NAMES,
    chain_context,
    load_stage,
    next_stage,
    prior_context,
    render_invocation,
)


def test_stage_order():
    assert STAGE_NAMES[0] == "research"
    assert STAGE_NAMES[-1] == "loop"
    assert "spec" in STAGE_NAMES


def test_next_stage():
    assert next_stage("research") == "propose"
    # A grill gate now sits between blueprint→spec and spec→tasks.
    assert next_stage("blueprint") == "grill-blueprint"
    assert next_stage("grill-blueprint") == "spec"
    assert next_stage("spec") == "grill-spec"
    assert next_stage("grill-spec") == "tasks"
    assert next_stage("loop") is None
    assert next_stage("unknown") is None


def test_grill_gate_stages_share_grill_template():
    # grill-blueprint / grill-spec reuse commands/grill.md, write a grill report.
    gb = load_stage("grill-blueprint")
    assert gb is not None
    assert gb.template_path.name == "grill.md"
    assert gb.artifact == "grill/blueprint.md"
    assert gb.exists is True  # commands/grill.md ships in the repo


def test_render_grill_stage_passes_target(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "architecture.md").write_text("ARCH_BODY")
    stage = load_stage("grill-blueprint")
    text = render_invocation(stage, ws)
    assert "--target blueprint" in text
    assert "ARCH_BODY" in text  # grills its upstream artifact


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


# --------------------------- verify full-chain context --------------------------- #
def _manifest(stages):
    return {"stages": stages}


def test_chain_context_none_for_non_verify(tmp_path):
    assert chain_context("spec", tmp_path) is None


def test_chain_context_none_when_manifest_absent(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    assert chain_context("verify", ws) is None


def test_chain_context_assembles_full_chain(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "research.md").write_text("R body")
    (ws / "spec.md").write_text("S body")
    manifest = _manifest([
        {"name": "research", "artifact": "research.md", "exists": True, "citations": 3},
        {"name": "spec", "artifact": "spec.md", "exists": True},
        {"name": "verify", "artifact": "verify/", "exists": False, "is_dir": True},
    ])
    (ws / "chain.json").write_text(json.dumps(manifest))

    ctx = chain_context("verify", ws)
    assert ctx is not None
    assert "R body" in ctx
    assert "S body" in ctx
    assert "3 citations" in ctx
    assert "artifact chain" in ctx


def test_chain_context_skips_dirs_and_missing(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "spec.md").write_text("S body")
    manifest = _manifest([
        {"name": "spec", "artifact": "spec.md", "exists": True},
        {"name": "implement-task", "artifact": "impl/", "exists": True, "is_dir": True},
        {"name": "tasks", "artifact": "tasks.md", "exists": False},
    ])
    (ws / "chain.json").write_text(json.dumps(manifest))

    ctx = chain_context("verify", ws)
    assert "S body" in ctx
    assert "impl/" not in ctx


def test_chain_context_bad_json_falls_back(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "chain.json").write_text("{not valid")
    assert chain_context("verify", ws) is None


def test_render_verify_uses_chain_when_present(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "research.md").write_text("RESEARCH_MARKER")
    (ws / "spec.md").write_text("SPEC_MARKER")
    manifest = _manifest([
        {"name": "research", "artifact": "research.md", "exists": True},
        {"name": "spec", "artifact": "spec.md", "exists": True},
    ])
    (ws / "chain.json").write_text(json.dumps(manifest))

    stage = load_stage("verify")
    text = render_invocation(stage, ws)
    assert "artifact chain" in text
    assert "RESEARCH_MARKER" in text
    assert "SPEC_MARKER" in text


def test_render_verify_falls_back_to_prior_artifact(tmp_path):
    # No chain.json → verify uses its single upstream artifact (spec.md).
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "spec.md").write_text("SPEC_ONLY_MARKER")
    stage = load_stage("verify")
    text = render_invocation(stage, ws)
    assert "SPEC_ONLY_MARKER" in text
    assert "artifact chain" not in text
    # And prior_context still resolves spec.md for verify.
    assert prior_context("verify", ws) == "SPEC_ONLY_MARKER"
