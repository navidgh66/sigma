"""Tests for cli.claude_md_check_run — the thin subprocess/agent wiring around
cli.claude_md_check's pure logic.
"""

from __future__ import annotations

from cli import claude_md_check_run as run
from cli.runner import AgentResult


class FakeRunner:
    """Stands in for AgentRunner: returns a canned reply, accepts role= like the real one."""

    def __init__(self, reply: str, ok: bool = True):
        self.reply = reply
        self.ok = ok

    def run(self, prompt, cwd=None, role="agent"):
        if not self.ok:
            return AgentResult(ok=False, output="", error="boom")
        return AgentResult(ok=True, output=self.reply)


def _clean_runner():
    return FakeRunner("")  # no FINDING lines → qualitative pass is clean


# --------------------------------------------------------------------------- #
# real_test_count
# --------------------------------------------------------------------------- #
def test_real_test_count_parses_collected_line(tmp_path):
    def fake_run(argv, **kwargs):
        class Proc:
            stdout = "807 tests collected in 0.42s\n"

        return Proc()

    n = run.real_test_count(tmp_path, runner=fake_run)
    assert n == 807


def test_real_test_count_singular_test(tmp_path):
    def fake_run(argv, **kwargs):
        class Proc:
            stdout = "1 test collected in 0.01s\n"

        return Proc()

    n = run.real_test_count(tmp_path, runner=fake_run)
    assert n == 1


def test_real_test_count_returns_none_on_subprocess_error(tmp_path):
    def boom(argv, **kwargs):
        raise OSError("pytest not found")

    n = run.real_test_count(tmp_path, runner=boom)
    assert n is None


def test_real_test_count_returns_none_on_unparseable_output(tmp_path):
    def fake_run(argv, **kwargs):
        class Proc:
            stdout = "some unrelated output\n"

        return Proc()

    n = run.real_test_count(tmp_path, runner=fake_run)
    assert n is None


# --------------------------------------------------------------------------- #
# run_check
# --------------------------------------------------------------------------- #
def test_run_check_missing_claude_md_is_error(tmp_path):
    result = run.run_check(tmp_path, make_agent=lambda: _clean_runner())
    assert result.ok is False
    assert "CLAUDE.md" in result.error


def test_run_check_local_md_absent_skips_silently(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nShort.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: _clean_runner(),
        test_count_fn=lambda root: None,
    )
    assert result.ok is True
    assert result.files_checked == ["CLAUDE.md"]


def test_run_check_local_md_present_checked_too(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nShort.\n")
    (tmp_path / "CLAUDE.local.md").write_text("# Local\nAlso short.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: _clean_runner(),
        test_count_fn=lambda root: None,
    )
    assert result.ok is True
    assert result.files_checked == ["CLAUDE.md", "CLAUDE.local.md"]


def test_run_check_clean_files_pass_gate(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nShort and clean.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: _clean_runner(),
        test_count_fn=lambda root: None,
    )
    assert result.gate.passed is True
    assert result.findings == []


def test_run_check_deterministic_finding_surfaces(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nTODO: finish this.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: _clean_runner(),
        test_count_fn=lambda root: None,
    )
    assert any("TODO" in f.message for f in result.findings)


def test_run_check_qualitative_finding_surfaces(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nWrite clean code.\n")
    qualitative = FakeRunner(
        "FINDING | MEDIUM | CLAUDE.md:2 | self-evident, would not cause a mistake if removed\n"
    )
    result = run.run_check(
        tmp_path,
        make_agent=lambda: qualitative,
        test_count_fn=lambda root: None,
    )
    assert any("self-evident" in f.message for f in result.findings)


def test_run_check_agent_failure_does_not_crash_qualitative_pass(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Title\nShort.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: FakeRunner("", ok=False),
        test_count_fn=lambda root: None,
    )
    assert result.ok is True  # a failed qualitative pass degrades, never crashes


def test_run_check_high_finding_fails_gate(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("See @missing.md for details.\n")
    result = run.run_check(
        tmp_path,
        make_agent=lambda: _clean_runner(),
        test_count_fn=lambda root: None,
    )
    assert result.gate.passed is False


# --------------------------------------------------------------------------- #
# write_report
# --------------------------------------------------------------------------- #
def test_write_report_writes_under_sigma_dir(tmp_path):
    out = run.write_report(tmp_path, "# report\nPASS")
    assert out == tmp_path / "sigma" / "claude-md-check.md"
    assert out.read_text() == "# report\nPASS\n"
