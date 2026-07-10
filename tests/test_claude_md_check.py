"""Tests for cli.claude_md_check — pure deterministic + LM-judge checks for
CLAUDE.md / CLAUDE.local.md against the sigma:2026-07-10 best-practice research
(target <200 lines, no pasted-code snippets, no stale @imports, no stale test
counts, no placeholders; a qualitative agent pass grades structure/specificity).
"""

from __future__ import annotations

from cli import claude_md_check as c


# --------------------------------------------------------------------------- #
# Deterministic: line count
# --------------------------------------------------------------------------- #
def test_length_ok_under_200_lines():
    findings = c.check_length("\n".join(["x"] * 50), "CLAUDE.md")
    assert findings == []


def test_length_warn_between_200_and_300():
    findings = c.check_length("\n".join(["x"] * 250), "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"
    assert findings[0].file == "CLAUDE.md"


def test_length_fail_over_300():
    findings = c.check_length("\n".join(["x"] * 350), "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].severity == "HIGH"


# --------------------------------------------------------------------------- #
# Deterministic: pasted code blocks
# --------------------------------------------------------------------------- #
def test_no_pasted_code_block_flag_when_short():
    text = "# Title\n```python\nprint(1)\n```\n"
    assert c.check_pasted_code_blocks(text, "CLAUDE.md") == []


def test_long_pasted_code_block_flagged():
    body = "\n".join(f"line {i}" for i in range(20))
    text = f"# Title\n```python\n{body}\n```\n"
    findings = c.check_pasted_code_blocks(text, "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"
    assert "file:line" in findings[0].message or "pointer" in findings[0].message


def test_unclosed_code_fence_does_not_crash():
    text = "# Title\n```python\nno closing fence\n"
    findings = c.check_pasted_code_blocks(text, "CLAUDE.md")
    assert findings == []  # nothing to flag, but must not raise


# --------------------------------------------------------------------------- #
# Deterministic: @path imports
# --------------------------------------------------------------------------- #
def test_import_resolves_no_finding(tmp_path):
    (tmp_path / "docs.md").write_text("hi")
    text = "See @docs.md for details."
    findings = c.check_imports(text, tmp_path / "CLAUDE.md")
    assert findings == []


def test_import_broken_flagged(tmp_path):
    text = "See @missing.md for details."
    findings = c.check_imports(text, tmp_path / "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].severity == "HIGH"
    assert "missing.md" in findings[0].message


def test_import_inside_backticks_not_checked(tmp_path):
    text = "Use `@missing.md` as a literal example, not an import."
    findings = c.check_imports(text, tmp_path / "CLAUDE.md")
    assert findings == []


def test_import_inside_fenced_code_block_not_checked(tmp_path):
    text = "```\n@missing.md\n```\n"
    findings = c.check_imports(text, tmp_path / "CLAUDE.md")
    assert findings == []


# --------------------------------------------------------------------------- #
# Deterministic: stale test-count claims
# --------------------------------------------------------------------------- #
def test_stale_test_count_matches_real_count_no_finding():
    text = "We have 807 pytest tests, ruff clean."
    findings = c.check_test_count_claims(text, "CLAUDE.md", real_count=807)
    assert findings == []


def test_stale_test_count_mismatch_flagged():
    text = "We have 779 pytest tests, ruff clean."
    findings = c.check_test_count_claims(text, "CLAUDE.md", real_count=807)
    assert len(findings) == 1
    assert findings[0].severity == "MEDIUM"
    assert "779" in findings[0].message and "807" in findings[0].message


def test_stale_test_count_no_claim_no_finding():
    text = "This file has no test count mentioned."
    findings = c.check_test_count_claims(text, "CLAUDE.md", real_count=807)
    assert findings == []


def test_stale_test_count_real_count_none_skips_check():
    """If the caller couldn't determine the real count, never guess/flag."""
    text = "We have 779 pytest tests."
    findings = c.check_test_count_claims(text, "CLAUDE.md", real_count=None)
    assert findings == []


# --------------------------------------------------------------------------- #
# Deterministic: placeholders
# --------------------------------------------------------------------------- #
def test_placeholder_todo_flagged():
    findings = c.check_placeholders("Some text.\nTODO: fill this in later.\n", "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].severity == "LOW"


def test_placeholder_tbd_flagged():
    findings = c.check_placeholders("Status: TBD\n", "CLAUDE.md")
    assert len(findings) == 1


def test_no_placeholder_no_finding():
    findings = c.check_placeholders("Everything here is finished.\n", "CLAUDE.md")
    assert findings == []


# --------------------------------------------------------------------------- #
# Aggregation: run_deterministic_checks
# --------------------------------------------------------------------------- #
def test_run_deterministic_checks_combines_all(tmp_path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("# Title\nTODO: write more.\n")
    findings = c.run_deterministic_checks(md.read_text(), "CLAUDE.md", tmp_path, real_test_count=None)
    assert any(f.severity == "LOW" for f in findings)  # the TODO


def test_run_deterministic_checks_on_clean_file_no_findings(tmp_path):
    md = tmp_path / "CLAUDE.md"
    md.write_text("# Title\nShort and clean.\n")
    findings = c.run_deterministic_checks(md.read_text(), "CLAUDE.md", tmp_path, real_test_count=None)
    assert findings == []


# --------------------------------------------------------------------------- #
# Qualitative: prompt building + parsing (reuses review's FINDING grammar)
# --------------------------------------------------------------------------- #
def test_build_qualitative_prompt_includes_content_and_rubric():
    prompt = c.build_qualitative_prompt("# CLAUDE.md\nsome content", "CLAUDE.md")
    assert "some content" in prompt
    assert "FINDING" in prompt  # instructs the output grammar


def test_parse_qualitative_findings_reuses_review_grammar():
    output = "FINDING | MEDIUM | CLAUDE.md:12 | vague instruction, not verifiable\n"
    findings = c.parse_qualitative_findings(output, "CLAUDE.md")
    assert len(findings) == 1
    assert findings[0].file == "CLAUDE.md"
    assert findings[0].line == 12
    assert findings[0].severity == "MEDIUM"


# --------------------------------------------------------------------------- #
# Gate (reuses review's severity law: FAIL on any CRITICAL/HIGH)
# --------------------------------------------------------------------------- #
def test_gate_passes_with_no_blocking_findings():
    from cli.review import Finding

    findings = [Finding(axis="claude-md", severity="LOW", file="CLAUDE.md", line=1, message="minor")]
    decision = c.gate(findings)
    assert decision.passed is True


def test_gate_fails_on_high_finding():
    from cli.review import Finding

    findings = [Finding(axis="claude-md", severity="HIGH", file="CLAUDE.md", line=1, message="broken import")]
    decision = c.gate(findings)
    assert decision.passed is False


def test_gate_passes_on_empty_findings():
    decision = c.gate([])
    assert decision.passed is True


# --------------------------------------------------------------------------- #
# render_report
# --------------------------------------------------------------------------- #
def test_render_report_includes_verdict_and_findings():
    from cli.review import Finding

    findings = [Finding(axis="claude-md", severity="HIGH", file="CLAUDE.md", line=5, message="too long")]
    decision = c.gate(findings)
    report = c.render_report(findings, decision, "CLAUDE.md")
    assert "CLAUDE.md" in report
    assert "too long" in report
    assert "FAIL" in report or "❌" in report
