"""Tests for cli.claude_md_scaffold_run — thin agent-driven scaffolding."""

from __future__ import annotations

from cli import claude_md_scaffold_run as run
from cli.runner import AgentResult


class FakeRunner:
    def __init__(self, reply: str, ok: bool = True):
        self.reply = reply
        self.ok = ok

    def run(self, prompt, cwd=None, role="agent"):
        if not self.ok:
            return AgentResult(ok=False, output="", error="boom")
        return AgentResult(ok=True, output=self.reply)


def test_scaffold_writes_repo_file(tmp_path):
    agent = FakeRunner("# myproject\n## What\nstuff\n## Why\nreason\n## How\ncommands\n")
    result = run.run_scaffold(tmp_path, target="repo", agent=agent)
    assert result.ok is True
    assert (tmp_path / "CLAUDE.md").read_text() == agent.reply.strip() + "\n"


def test_scaffold_writes_local_file(tmp_path):
    agent = FakeRunner("# myproject (local)\n## How\npersonal stuff\n")
    result = run.run_scaffold(tmp_path, target="local", agent=agent)
    assert result.ok is True
    assert (tmp_path / "CLAUDE.local.md").exists()


def test_scaffold_refuses_to_overwrite_without_force(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("existing content\n")
    agent = FakeRunner("# new content\n")
    result = run.run_scaffold(tmp_path, target="repo", agent=agent)
    assert result.ok is False
    assert "already exists" in result.error
    assert (tmp_path / "CLAUDE.md").read_text() == "existing content\n"  # untouched


def test_scaffold_overwrites_with_force(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("existing content\n")
    agent = FakeRunner("# new content\n")
    result = run.run_scaffold(tmp_path, target="repo", agent=agent, force=True)
    assert result.ok is True
    assert (tmp_path / "CLAUDE.md").read_text() == "# new content\n"


def test_scaffold_falls_back_to_skeleton_on_agent_failure(tmp_path):
    agent = FakeRunner("", ok=False)
    result = run.run_scaffold(tmp_path, target="repo", agent=agent)
    assert result.ok is True
    assert result.used_skeleton_fallback is True
    text = (tmp_path / "CLAUDE.md").read_text()
    assert "## What" in text


def test_scaffold_falls_back_to_skeleton_on_empty_output(tmp_path):
    agent = FakeRunner("   ")
    result = run.run_scaffold(tmp_path, target="repo", agent=agent)
    assert result.ok is True
    assert result.used_skeleton_fallback is True


def test_scaffold_dry_run_writes_nothing(tmp_path):
    agent = FakeRunner("# generated content\n")
    result = run.run_scaffold(tmp_path, target="repo", agent=agent, dry_run=True)
    assert result.ok is True
    assert not (tmp_path / "CLAUDE.md").exists()
    assert result.prompt  # prompt returned for preview
