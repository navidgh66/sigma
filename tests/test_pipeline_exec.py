from cli.pipeline import execute_stage, prior_context, render_invocation
from cli.runner import AgentResult, AgentRunner


class FakeRunner(AgentRunner):
    def __init__(self, output="generated content", ok=True):
        super().__init__()
        self._output = output
        self._ok = ok

    def available(self):
        return True

    def run(self, prompt, cwd=None):
        self.last_prompt = prompt
        return AgentResult(ok=self._ok, output=self._output)


def test_prior_context_reads_upstream(tmp_path):
    (tmp_path / "research.md").write_text("RESEARCH BODY")
    ctx = prior_context("propose", tmp_path)
    assert ctx == "RESEARCH BODY"


def test_prior_context_none_for_research(tmp_path):
    assert prior_context("research", tmp_path) is None


def test_render_invocation_includes_prior(tmp_path):
    (tmp_path / "spec.md").write_text("THE SPEC")
    stage_text = render_invocation(_stage("tasks"), tmp_path)
    assert "THE SPEC" in stage_text
    assert "input: spec.md" in stage_text


def test_execute_stage_writes_file_artifact(tmp_path):
    res = execute_stage("spec", tmp_path, agent=FakeRunner("# Spec\nbody"))
    assert res.ok is True
    assert (tmp_path / "spec.md").read_text() == "# Spec\nbody"


def test_execute_stage_dir_artifact_writes_log(tmp_path):
    res = execute_stage("implement-task", tmp_path, agent=FakeRunner("did the work"))
    assert res.ok is True
    assert (tmp_path / "impl").is_dir()
    assert (tmp_path / "implement-task.log.md").read_text() == "did the work"


def test_execute_stage_failure_no_write(tmp_path):
    res = execute_stage("spec", tmp_path, agent=FakeRunner("x", ok=False))
    assert res.ok is False
    assert not (tmp_path / "spec.md").exists()


# helper
def _stage(name):
    from cli.pipeline import load_stage

    return load_stage(name)
