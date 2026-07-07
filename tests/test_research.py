from datetime import date

from cli.models import ModelResult
from cli.research import aggregate, research, run_research
from cli.research_brief import build_prompt


def test_build_prompt_contains_topic():
    p = build_prompt("graph neural nets")
    assert "graph neural nets" in p
    assert "source" in p.lower()


def _fake_runner_factory(mapping):
    def runner(model, prompt, deep=False):
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

    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    assert out.exists()
    body = out.read_text()
    assert "claude says hi" in body
    assert out.name == "research.md"


def test_build_prompt_deep_demands_web_search():
    quick = build_prompt("t", deep=False)
    deep = build_prompt("t", deep=True)
    assert "web-search" in deep or "web search" in deep.lower()
    assert "do NOT answer from memory" in deep
    # Quick brief stays lean (no web-search demand).
    assert "do NOT answer from memory" not in quick


def test_aggregate_marks_deep_mode():
    results = [ModelResult("claude", True, "x")]
    quick_doc = aggregate("t", results, today=date(2026, 6, 16), deep=False)
    deep_doc = aggregate("t", results, today=date(2026, 6, 16), deep=True)
    assert "Mode: quick" in quick_doc
    assert "Mode: deep (web-grounded)" in deep_doc


def test_run_research_forwards_deep_to_runner():
    seen = {}

    def runner(model, prompt, deep=False):
        seen[model] = deep
        return ModelResult(model, True, "ok")

    run_research("t", ["claude", "gpt"], runner=runner, deep=True)
    assert seen == {"claude": True, "gpt": True}


# --------------------------- web mode (quick web-grounded) --------------------------- #
def test_build_prompt_web_demands_search_but_lighter():
    web = build_prompt("t", web=True)
    quick = build_prompt("t", deep=False)
    assert "search the web" in web.lower()
    assert "QUICK" in web or "quick" in web
    # Web brief differs from the from-memory quick brief.
    assert web != quick


def test_build_prompt_deep_wins_over_web():
    both = build_prompt("t", deep=True, web=True)
    deep = build_prompt("t", deep=True)
    assert both == deep  # deep takes precedence


def test_aggregate_marks_web_mode():
    results = [ModelResult("claude", True, "x")]
    doc = aggregate("t", results, today=date(2026, 6, 16), web=True)
    assert "Mode: web (quick web-grounded)" in doc


def test_run_research_web_enables_websearch_flag():
    seen = {}

    def runner(model, prompt, deep=False):
        seen[model] = deep  # `deep` arg = web_search toggle in run_research
        return ModelResult(model, True, "ok")

    run_research("t", ["claude", "gpt"], runner=runner, web=True)
    # web mode activates the adapter web-search path (passed as the deep arg).
    assert seen == {"claude": True, "gpt": True}


# --------------------------- manual findings --------------------------- #
def test_read_manual_findings_empty_dir_returns_empty(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    ws.mkdir()
    assert _read_manual_findings(ws) == []


def test_read_manual_findings_missing_dir_returns_empty(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    ws.mkdir()
    # no manual/ subdir created at all
    assert _read_manual_findings(ws) == []


def test_read_manual_findings_reads_files(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    manual = ws / "manual"
    manual.mkdir(parents=True)
    (manual / "notes.md").write_text("Found Y (src: http://example.com)")
    results = _read_manual_findings(ws)
    assert len(results) == 1
    assert results[0].model == "manual:notes.md"
    assert results[0].ok is True
    assert "Found Y" in results[0].text


def test_read_manual_findings_skips_non_utf8_file(tmp_path):
    from cli.research import _read_manual_findings
    ws = tmp_path / "ws"
    manual = ws / "manual"
    manual.mkdir(parents=True)
    # Write invalid UTF-8 bytes directly (not valid text in any UTF-8 decode).
    (manual / "bad_encoding.md").write_bytes(b"\xff\xfe\x00\x01invalid utf8")
    (manual / "good.md").write_text("Valid finding.")
    results = _read_manual_findings(ws)
    # The bad file is skipped (no crash); the good file still comes through.
    assert len(results) == 1
    assert results[0].model == "manual:good.md"


# --------------------------- search-tool fan-out --------------------------- #
def test_run_research_includes_search_tools():
    from cli.research import run_research

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model}-findings")

    def search_runner(tool, prompt, deep=False):
        return ModelResult(tool, True, f"{tool}-findings")

    results = run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner, search_runner=search_runner
    )
    models = {r.model for r in results}
    assert models == {"claude", "firecrawl"}


def test_run_research_passes_bare_topic_to_search_tools_not_full_brief():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["query"] = query
        return ModelResult(tool, True, "tool-findings")

    run_research("my topic", ["claude"], tools=["firecrawl"], runner=model_runner, search_runner=search_runner)
    assert seen["query"] == "my topic"


def test_run_research_deep_true_passes_deep_to_search_tools():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["deep"] = deep
        return ModelResult(tool, True, "tool-findings")

    run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner,
        search_runner=search_runner, deep=True,
    )
    assert seen["deep"] is True


def test_run_research_web_only_does_not_set_deep_on_search_tools():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["deep"] = deep
        return ModelResult(tool, True, "tool-findings")

    run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner,
        search_runner=search_runner, web=True,
    )
    assert seen["deep"] is False


# --------------------------- synthesis --------------------------- #
def test_synthesize_calls_runner_with_all_results():
    from cli.research import synthesize

    seen = {}

    def fake_runner(prompt):
        seen["prompt"] = prompt
        return "Claim X confirmed by 2 sources."

    results = [
        ModelResult("claude", True, "Claim X (src: a)"),
        ModelResult("firecrawl", True, "Claim X (src: b)"),
    ]
    body = synthesize("topic", results, runner=fake_runner)
    assert "Claim X confirmed by 2 sources." in body
    assert "topic" in seen["prompt"]
    assert "Claim X (src: a)" in seen["prompt"]


def test_synthesize_falls_back_on_runner_failure():
    from cli.research import synthesize

    def failing_runner(prompt):
        raise RuntimeError("boom")

    results = [ModelResult("claude", True, "finding")]
    body = synthesize("topic", results, runner=failing_runner)
    # Falls back to the prior static placeholder text, never raises.
    assert "cross-reference" in body.lower()


def test_aggregate_uses_real_synthesis():
    from cli.research import aggregate

    def fake_synth_runner(prompt):
        return "REAL SYNTHESIS OUTPUT"

    results = [ModelResult("claude", True, "x")]
    doc = aggregate("t", results, today=date(2026, 6, 16), synthesis_runner=fake_synth_runner)
    assert "REAL SYNTHESIS OUTPUT" in doc


def test_aggregate_falls_back_to_placeholder_when_synthesis_runner_missing():
    from cli.research import aggregate

    results = [ModelResult("claude", True, "x")]
    doc = aggregate("t", results, today=date(2026, 6, 16))
    assert "cross-reference" in doc.lower()


# --------------------------- end-to-end wiring --------------------------- #
def test_research_end_to_end_includes_manual_findings(tmp_path):
    from cli.research import research

    ws = tmp_path / "specs" / "2026-06-16-topic"
    manual = ws / "manual"
    manual.mkdir(parents=True)
    (manual / "extra.md").write_text("Manually added finding.")

    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    body = out.read_text()
    assert "Manually added finding" in body
    assert "manual:extra.md" in body


def test_claude_synthesis_runner_returns_text_on_success(monkeypatch):
    import cli.research as research_mod
    from cli.research import claude_synthesis_runner

    def fake_run_model(model, prompt):
        assert model == "claude"
        return ModelResult(model, True, "synthesized findings")

    monkeypatch.setattr(research_mod, "run_model", fake_run_model)
    assert claude_synthesis_runner("some prompt") == "synthesized findings"


def test_claude_synthesis_runner_returns_empty_on_failure(monkeypatch):
    import cli.research as research_mod
    from cli.research import claude_synthesis_runner

    def fake_run_model(model, prompt):
        return ModelResult(model, False, "", error="CLI not installed", skipped=True)

    monkeypatch.setattr(research_mod, "run_model", fake_run_model)
    assert claude_synthesis_runner("some prompt") == ""


def test_research_unchanged_when_no_tools_or_manual_findings(tmp_path):
    """Regression lock: empty tools + no manual/ dir behaves like the old module,
    except the Synthesis section (which is intentionally now real-or-fallback
    text instead of the old hardcoded string — same fallback text, same spot).
    """
    from cli.research import research

    ws = tmp_path / "specs" / "2026-06-16-topic"

    def runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model} says hi")

    out = research("topic", ["claude"], ws, runner=runner, today=date(2026, 6, 16))
    body = out.read_text()
    assert "claude says hi" in body
    assert "cross-reference" in body.lower()  # fallback synthesis text, unchanged wording
    assert "manual:" not in body  # no manual dir → nothing manual rendered
