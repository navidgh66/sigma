"""Tests for cli/review_run's graph-aware Impact section (Task 8).

Reuses the same fake-AgentRunner harness shape as tests/test_review.py: a
`FakeRunner` returning a canned per-axis reply and a `_fake_cmd_runner` that hands
back a fixed diff for git/gh. The key fixtures are a temp `root` with / without a
`graphify-out/graph.json`.
"""

import json

from cli import review_run

# A minimal diff touching one file the graph will know about.
FOO_DIFF = (
    "diff --git a/cli/foo.py b/cli/foo.py\n"
    "index 111..222 100644\n"
    "--- a/cli/foo.py\n"
    "+++ b/cli/foo.py\n"
    "@@ -1 +1,2 @@\n"
    "+x = 1\n"
)


class FakeRunner:
    """Stands in for AgentRunner: returns a canned reply per axis prompt."""

    def __init__(self, reply: str, ok: bool = True):
        self.reply = reply
        self.ok = ok

    def run(self, prompt: str, cwd=None):
        from cli.runner import AgentResult

        if not self.ok:
            return AgentResult(ok=False, output="", error="boom")
        return AgentResult(ok=True, output=self.reply)


def _make_passing_runner():
    # Fresh instance each call → the three axes stay distinct (maker≠checker).
    return FakeRunner("FINDING | LOW | cli/foo.py:1 | ok\nVERDICT: PASS")


def _fake_diff(argv, **kwargs):
    class Proc:
        returncode = 0
        stdout = FOO_DIFF
        stderr = ""

    return Proc()


def test_review_appends_impact_when_graph_present(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps(
        {"nodes": [{"name": "Foo", "file": "cli/foo.py"}], "edges": []}))

    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=_make_passing_runner,
        reviews_dir=tmp_path / "reviews",
        cmd_runner=_fake_diff,
    )
    assert res.ok
    assert "## Impact (knowledge graph)" in res.report
    assert "cli/foo.py" in res.report


def test_review_report_byte_identical_without_graph(tmp_path):
    # No graphify-out/graph.json → report must equal the no-graph baseline.
    res = review_run.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=_make_passing_runner,
        reviews_dir=tmp_path / "reviews",
        cmd_runner=_fake_diff,
    )
    assert res.ok
    assert "## Impact (knowledge graph)" not in res.report
