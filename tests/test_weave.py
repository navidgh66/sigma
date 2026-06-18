"""Tests for cli.weave — orchestration with a fake agent."""

from __future__ import annotations

import json

from cli.runner import AgentResult
from cli.weave import CHAIN_HTML, CHAIN_JSON, build_weave_prompt, run_weave


class FakeAgent:
    def __init__(self, output, ok=True, error=None):
        self._output = output
        self._ok = ok
        self._error = error

    def run(self, prompt, cwd=None):
        return AgentResult(ok=self._ok, output=self._output, error=self._error)


def _workspace(tmp_path, **files):
    ws = tmp_path / "ws"
    ws.mkdir()
    for name, content in files.items():
        (ws / name).write_text(content)
    return ws


_GOOD_HTML = "<!DOCTYPE html><html><body><h1>research</h1><h2>spec</h2></body></html>"


# --------------------------- prompt building --------------------------- #
def test_prompt_embeds_present_artifacts(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R findings", "spec.md": "# S body"})
    prompt = build_weave_prompt(ws, topic="auth")
    assert "auth" in prompt
    assert "R findings" in prompt
    assert "S body" in prompt
    # Must not lead with a dash (claude -p would parse it as a flag).
    assert not prompt.lstrip().startswith("-")


# --------------------------- end to end --------------------------- #
def test_run_weave_writes_both_outputs(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R", "spec.md": "# S"})

    res = run_weave(ws, topic="auth", slug=ws.name, agent=FakeAgent(_GOOD_HTML))

    assert res.ok
    assert (ws / CHAIN_JSON).exists()
    assert (ws / CHAIN_HTML).exists()
    assert res.html_problems == []
    manifest = json.loads((ws / CHAIN_JSON).read_text())
    assert manifest["topic"] == "auth"


def test_run_weave_strips_html_fence(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R", "spec.md": "# S"})
    fenced = f"```html\n{_GOOD_HTML}\n```"
    res = run_weave(ws, agent=FakeAgent(fenced))
    assert res.ok
    assert (ws / CHAIN_HTML).read_text().startswith("<!DOCTYPE html>")


def test_run_weave_manifest_written_even_when_agent_fails(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R"})
    res = run_weave(ws, agent=FakeAgent("", ok=False, error="boom"))
    assert not res.ok
    assert "boom" in res.error
    # Manifest is independent of the agent — it must still exist.
    assert res.manifest_path is not None
    assert (ws / CHAIN_JSON).exists()


def test_run_weave_surfaces_html_problems(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R", "spec.md": "# S"})
    # Missing the 'spec' section.
    bad = "<!DOCTYPE html><html><body><h1>research</h1></body></html>"
    res = run_weave(ws, agent=FakeAgent(bad))
    assert res.ok  # written; problems surfaced separately
    assert any("spec" in p for p in res.html_problems)


def test_run_weave_fence_only_output_does_not_write_corrupt_html(tmp_path):
    # Agent returns a bare fence — strips to "". Must NOT write an empty
    # chain.html and must NOT report success.
    ws = _workspace(tmp_path, **{"research.md": "# R"})
    res = run_weave(ws, agent=FakeAgent("```html\n```"))
    assert not res.ok
    assert not (ws / CHAIN_HTML).exists()
    # Manifest still written (agent-independent).
    assert (ws / CHAIN_JSON).exists()


def test_run_weave_strips_trailing_newline_after_fence(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R", "spec.md": "# S"})
    fenced = f"```html\n{_GOOD_HTML}\n```\n"
    res = run_weave(ws, agent=FakeAgent(fenced))
    assert res.ok
    html = (ws / CHAIN_HTML).read_text()
    assert html.startswith("<!DOCTYPE html>")
    assert "```" not in html


def test_run_weave_dry_run_does_not_call_agent(tmp_path):
    ws = _workspace(tmp_path, **{"research.md": "# R"})

    class Boom:
        def run(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError("agent should not run in dry-run")

    res = run_weave(ws, agent=Boom(), dry_run=True)
    assert res.ok
    assert "R" in res.prompt
    assert not (ws / CHAIN_JSON).exists()
