"""Tests for cli.learn — codebase-learning orchestration with a fake agent."""

from __future__ import annotations

import json

from cli.learn import (
    ARCH_HEADER,
    TOUR_HEADER,
    build_learn_prompt,
    run_learn,
    split_output,
)  # build_learn_prompt used by the byte-identical regression test
from cli.runner import AgentResult


class FakeAgent:
    def __init__(self, output, ok=True, error=None):
        self._output = output
        self._ok = ok
        self._error = error

    def run(self, prompt, cwd=None):
        return AgentResult(ok=self._ok, output=self._output, error=self._error)


def _vendor(tmp_path):
    """A minimal vendor tree with both learn skills present."""
    v = tmp_path / "vendor"
    for slug in ("code-tour", "codebase-onboarding"):
        d = v / slug
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {slug}\nfollow {slug} conventions")
    return v


# --------------------------- prompt building --------------------------- #
def test_prompt_injects_skills_and_headers(tmp_path):
    vendor = _vendor(tmp_path)
    prompt = build_learn_prompt(tmp_path, persona="new dev", vendor=vendor)
    assert "code-tour" in prompt
    assert "codebase-onboarding" in prompt
    assert ARCH_HEADER in prompt
    assert TOUR_HEADER in prompt
    assert "new dev" in prompt


def test_prompt_does_not_start_with_dash(tmp_path):
    # Regression: a leading '-' makes `claude -p <prompt>` parse the prompt as an
    # option flag and the agent run fails. The injected prompt must never lead
    # with a dash.
    vendor = _vendor(tmp_path)
    prompt = build_learn_prompt(tmp_path, persona=None, vendor=vendor)
    assert not prompt.lstrip().startswith("-")


# --------------------------- output splitting --------------------------- #
def test_split_output_separates_sections():
    out = f"{ARCH_HEADER}\n# Arch\nbody\n{TOUR_HEADER}\n{{\"title\": \"T\"}}"
    arch, tour = split_output(out)
    assert "# Arch" in arch
    assert tour == '{"title": "T"}'


def test_split_output_strips_json_fence():
    out = f'{ARCH_HEADER}\nA\n{TOUR_HEADER}\n```json\n{{"title": "T"}}\n```'
    _, tour = split_output(out)
    assert tour == '{"title": "T"}'


# --------------------------- end to end --------------------------- #
def test_run_learn_writes_both_artifacts(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    vendor = _vendor(tmp_path)

    tour = {
        "title": "Repo Tour",
        "steps": [{"description": "entry", "file": "main.py", "line": 1}],
    }
    output = f"{ARCH_HEADER}\n# Architecture\nIt is a script.\n{TOUR_HEADER}\n{json.dumps(tour)}"

    res = run_learn(repo, agent=FakeAgent(output), vendor=vendor)
    assert res.ok
    assert res.architecture_path.exists()
    assert "It is a script." in res.architecture_path.read_text()
    assert res.tour_path.exists()
    assert res.tour_path.name == "repo-tour.tour"
    assert res.tour_problems == []
    # The written tour is valid JSON.
    json.loads(res.tour_path.read_text())


def test_run_learn_surfaces_tour_anchor_problems(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = _vendor(tmp_path)
    tour = {"title": "T", "steps": [{"description": "x", "file": "ghost.py", "line": 1}]}
    output = f"{ARCH_HEADER}\nA\n{TOUR_HEADER}\n{json.dumps(tour)}"

    res = run_learn(repo, agent=FakeAgent(output), vendor=vendor)
    assert res.ok  # still writes; problems surfaced separately
    assert res.tour_path.exists()
    assert any("file not found" in p for p in res.tour_problems)


def test_run_learn_dry_run_does_not_call_agent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = _vendor(tmp_path)

    class Boom:
        def run(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError("agent should not run in dry-run")

    res = run_learn(repo, agent=Boom(), vendor=vendor, dry_run=True)
    assert res.ok
    assert ARCH_HEADER in res.prompt
    assert res.architecture_path is None


def test_run_learn_agent_failure(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = _vendor(tmp_path)
    res = run_learn(repo, agent=FakeAgent("", ok=False, error="boom"), vendor=vendor)
    assert not res.ok
    assert "boom" in res.error


def test_run_learn_empty_sections_fails(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = _vendor(tmp_path)
    res = run_learn(repo, agent=FakeAgent("garbage with no headers"), vendor=vendor)
    assert not res.ok
    assert "neither" in res.error


def test_run_learn_bad_tour_json_flagged(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vendor = _vendor(tmp_path)
    output = f"{ARCH_HEADER}\nA\n{TOUR_HEADER}\n{{not valid json"
    res = run_learn(repo, agent=FakeAgent(output), vendor=vendor)
    assert res.ok  # architecture still written
    assert res.tour_path is None
    assert any("did not parse" in p for p in res.tour_problems)


# --------------------------- graphify integration --------------------------- #
def _good_output():
    tour = {"title": "T", "steps": [{"description": "x", "file": "main.py", "line": 1}]}
    return f"{ARCH_HEADER}\n# Arch\nbody\n{TOUR_HEADER}\n{json.dumps(tour)}"


def test_no_graph_prompt_byte_identical_to_baseline(tmp_path):
    # Regression lock: with graphify absent (no report), the learn prompt must be
    # exactly the prompt sigma built before graphify existed.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    vendor = _vendor(tmp_path)

    baseline = build_learn_prompt(repo.resolve(), persona=None, vendor=vendor)
    res = run_learn(
        repo, agent=FakeAgent(_good_output()), vendor=vendor,
        which=lambda exe: None,  # graphify not installed
    )
    assert res.ok
    assert res.graph_built is False
    assert res.prompt == baseline


def test_graph_built_when_installed_runs_extract(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    vendor = _vendor(tmp_path)
    calls = []

    def graph_runner(argv, cwd):
        calls.append((argv, cwd))
        # Simulate graphify writing its report.
        out = (repo.resolve()) / "graphify-out"
        out.mkdir(parents=True, exist_ok=True)
        (out / "GRAPH_REPORT.md").write_text("# Graph\nGod node: main.py")
        return 0

    res = run_learn(
        repo, agent=FakeAgent(_good_output()), vendor=vendor,
        which=lambda exe: "/bin/graphify",
        graph_runner=graph_runner,
    )
    assert res.ok
    assert res.graph_built is True
    assert calls and calls[0][0][:2] == ["graphify", "extract"]
    # The report got injected into the prompt.
    assert "God node: main.py" in res.prompt


def test_graph_build_failure_still_learns(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    vendor = _vendor(tmp_path)

    res = run_learn(
        repo, agent=FakeAgent(_good_output()), vendor=vendor,
        which=lambda exe: "/bin/graphify",
        graph_runner=lambda argv, cwd: 1,  # graphify failed
    )
    assert res.ok  # fail-safe: learn proceeds
    assert res.graph_built is False
    assert res.graph_note and "exited 1" in res.graph_note


def test_no_graph_flag_skips_build(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n")
    vendor = _vendor(tmp_path)

    def boom(argv, cwd):  # pragma: no cover - must not run
        raise AssertionError("graph build must be skipped when build_graph=False")

    res = run_learn(
        repo, agent=FakeAgent(_good_output()), vendor=vendor,
        build_graph=False, which=lambda exe: "/bin/graphify", graph_runner=boom,
    )
    assert res.ok
    assert res.graph_built is False
