from datetime import date

from cli.models import ModelResult
from cli.research import aggregate, build_prompt, research, run_research


def test_build_prompt_contains_topic():
    p = build_prompt("graph neural nets")
    assert "graph neural nets" in p
    assert "source" in p.lower()


def _fake_runner_factory(mapping):
    def runner(model, prompt):
        return mapping[model]
    return runner


def test_run_research_parallel_collects_all():
    mapping = {
        "claude": ModelResult("claude", True, "c-findings"),
        "gpt": ModelResult("gpt", True, "g-findings"),
    }
    results = run_research("topic", ["claude", "gpt"], runner=_fake_runner_factory(mapping))
    models = {r.model for r in results}
    assert models == {"claude", "gpt"}


def test_aggregate_reports_coverage():
    results = [
        ModelResult("claude", True, "Found X (src: http://a)"),
        ModelResult("gemini", False, "", error="CLI not installed", skipped=True),
        ModelResult("gpt", False, "", error="boom"),
    ]
    doc = aggregate("my topic", results, today=date(2026, 6, 16))
    assert "# Research: my topic" in doc
    assert "2026-06-16" in doc
    assert "✅ ran" in doc
    assert "⏭️ skipped" in doc
    assert "❌ failed" in doc
    assert "Found X" in doc


def test_aggregate_all_skipped_warns():
    results = [
        ModelResult("claude", False, "", error="CLI not installed", skipped=True),
    ]
    doc = aggregate("t", results)
    assert "No models produced findings" in doc


def test_research_end_to_end_writes_file(tmp_path):
    ws = tmp_path / "specs" / "2026-06-16-topic"

    def runner(model, prompt):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    assert out.exists()
    body = out.read_text()
    assert "claude says hi" in body
    assert out.name == "research.md"
