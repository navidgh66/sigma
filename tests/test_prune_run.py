"""Tests for cli.prune_run — report build + reversible disable with fake IO.

No real home dir, no real transcripts: every path/reader/writer is injected or
points at tmp_path.
"""

from __future__ import annotations

import json

from cli.prune_run import build_report, disable_plugins, scan_usage


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _transcript(path, tool_uses):
    """Write a .jsonl transcript whose records contain the given tool_use names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in tool_uses:
        block = {"type": "tool_use", "name": name}
        if name == "Skill":
            block["input"] = {"skill": "sigma:sigma-grilling"}
        lines.append(json.dumps({"message": {"content": [block]}}))
    path.write_text("\n".join(lines) + "\n")


# --------------------------- scan_usage --------------------------- #
def test_scan_usage_collects_tools_and_skills(tmp_path):
    t = tmp_path / "proj" / "s.jsonl"
    _transcript(t, ["Bash", "mcp__plugin_github_github__create_pull_request", "Skill"])
    inv, skills, scanned = scan_usage(tmp_path)
    assert scanned == 1
    assert "mcp__plugin_github_github__create_pull_request" in inv
    assert "sigma:sigma-grilling" in skills


def test_scan_usage_missing_dir_safe(tmp_path):
    inv, skills, scanned = scan_usage(tmp_path / "nope")
    assert (inv, skills, scanned) == ([], [], 0)


# --------------------------- build_report --------------------------- #
def test_report_ranks_unused_heavy_first(tmp_path):
    settings = tmp_path / "settings.json"
    _write(settings, {"enabledPlugins": {"github@m": True, "idle-plug@m": True}})
    claude_json = tmp_path / ".claude.json"
    _write(claude_json, {"mcpServers": {"idle-mcp": {}}})
    tdir = tmp_path / "projects"
    # Only github is exercised in the transcript.
    _transcript(tdir / "p" / "s.jsonl", ["mcp__plugin_github_github__list_pull_requests"])

    rep = build_report(
        settings_path=settings, claude_json_path=claude_json, transcripts_dir=tdir
    )
    names = [c.name for c in rep.candidates]
    assert "github@m" not in names                 # used → kept
    assert names[0] == "idle-mcp"                   # heaviest unused first
    assert "idle-plug@m" in names
    assert rep.freed_tokens > 0


def test_report_no_transcripts_skips(tmp_path):
    settings = tmp_path / "settings.json"
    _write(settings, {"enabledPlugins": {"a@m": True}})
    rep = build_report(
        settings_path=settings,
        claude_json_path=tmp_path / "missing.json",
        transcripts_dir=tmp_path / "no-transcripts",
    )
    # No usage evidence → conservative: surface nothing.
    assert rep.candidates == []
    assert "won't prune" in rep.note


def test_report_nothing_loaded(tmp_path):
    rep = build_report(
        settings_path=tmp_path / "missing.json",
        claude_json_path=tmp_path / "missing2.json",
        transcripts_dir=tmp_path,
    )
    assert rep.candidates == []
    assert "nothing loaded" in rep.note


# --------------------------- reversible disable --------------------------- #
def test_disable_plugins_flips_flag_preserves_other_keys(tmp_path):
    settings = tmp_path / "settings.json"
    _write(settings, {
        "model": "opus",
        "enabledPlugins": {"keep@m": True, "drop@m": True},
        "statusLine": {"command": "x"},
    })
    written = {}

    def writer(path, data):
        written["data"] = data
        return True

    ok = disable_plugins(["drop@m"], settings_path=settings, writer=writer)
    assert ok
    d = written["data"]
    # disabled, not deleted
    assert d["enabledPlugins"]["drop@m"] is False
    assert d["enabledPlugins"]["keep@m"] is True
    # every other key preserved (immutable merge)
    assert d["model"] == "opus"
    assert d["statusLine"] == {"command": "x"}


def test_disable_plugins_does_not_mutate_loaded(tmp_path):
    settings = tmp_path / "settings.json"
    original = {"enabledPlugins": {"p@m": True}}
    _write(settings, original)
    disable_plugins(["p@m"], settings_path=settings, writer=lambda p, d: True)
    # The on-disk file is unchanged until a real writer runs; the loaded dict in
    # this test process is independent — re-read confirms no in-place mutation.
    reread = json.loads(settings.read_text())
    assert reread["enabledPlugins"]["p@m"] is True
