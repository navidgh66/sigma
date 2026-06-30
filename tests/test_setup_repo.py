"""Tests for cli.setup_repo — one-shot per-repo bootstrap (agent + FS injected)."""

from __future__ import annotations

import json

from cli import setup_repo as sr


class _LearnRes:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error


def _no_agent(calls):
    """A learn_fn that records the root and never spawns an agent."""
    return lambda root: calls.append(root) or _LearnRes(ok=True)


# --------------------------- config step --------------------------- #
def test_writes_config_when_missing(tmp_path):
    res = sr.run_setup_repo(tmp_path, domains=["nlp"], no_learn=True)
    assert res.config_written
    assert (tmp_path / "sigma.config.yml").exists()


def test_keeps_existing_config(tmp_path):
    (tmp_path / "sigma.config.yml").write_text("name: keep\ndomains: [rl]\n")
    res = sr.run_setup_repo(tmp_path, no_learn=True)
    assert res.config_written is False
    assert "keep" in (tmp_path / "sigma.config.yml").read_text()


# --------------------------- hook step --------------------------- #
def test_adds_session_hook(tmp_path):
    res = sr.run_setup_repo(tmp_path, no_learn=True)
    assert res.hook_added
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    cmds = [
        h["command"]
        for e in data["hooks"]["SessionStart"]
        for h in e.get("hooks", [])
    ]
    assert any("session-context" in c for c in cmds)


def test_hook_idempotent(tmp_path):
    sr.run_setup_repo(tmp_path, no_learn=True)
    res2 = sr.run_setup_repo(tmp_path, no_learn=True)
    assert res2.hook_added is False  # already configured second time
    # still exactly one SessionStart entry
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(data["hooks"]["SessionStart"]) == 1


# --------------------------- CLAUDE.local step --------------------------- #
def test_writes_claude_local_and_gitignore(tmp_path):
    res = sr.run_setup_repo(tmp_path, no_learn=True)
    assert res.local_written
    assert (tmp_path / "CLAUDE.local.md").exists()
    assert "sigma:learn" in (tmp_path / "CLAUDE.local.md").read_text()
    assert "CLAUDE.local.md" in (tmp_path / ".gitignore").read_text()


# --------------------------- map step --------------------------- #
def test_runs_learn_by_default(tmp_path):
    calls = []
    res = sr.run_setup_repo(tmp_path, learn_fn=_no_agent(calls))
    assert calls == [tmp_path.resolve()]
    assert res.learned is True


def test_no_learn_skips_agent(tmp_path):
    calls = []
    res = sr.run_setup_repo(tmp_path, no_learn=True, learn_fn=_no_agent(calls))
    assert calls == []
    assert res.learned is False
    assert res.learn_skipped_reason == "--no-learn"


def test_skips_learn_when_artifacts_exist(tmp_path):
    (tmp_path / "ARCHITECTURE.md").write_text("# already here\n")
    calls = []
    res = sr.run_setup_repo(tmp_path, learn_fn=_no_agent(calls))
    assert calls == []  # must not re-spawn over an existing map
    assert res.learned is False
    assert "exist" in res.learn_skipped_reason


def test_learn_failure_recorded_not_raised(tmp_path):
    res = sr.run_setup_repo(tmp_path, learn_fn=lambda root: _LearnRes(ok=False, error="boom"))
    assert res.learned is False
    assert "boom" in res.learn_skipped_reason


# --------------------------- end to end --------------------------- #
def test_fresh_repo_gets_all_artifacts(tmp_path):
    calls = []
    res = sr.run_setup_repo(tmp_path, domains=["nlp"], learn_fn=_no_agent(calls))
    assert res.config_written and res.hook_added and res.local_written and res.learned
    assert (tmp_path / "sigma.config.yml").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / "CLAUDE.local.md").exists()
    assert len(res.steps) == 4
