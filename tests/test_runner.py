import subprocess

from cli.runner import AgentRunner, write_artifact


def _fake_proc(returncode=0, stdout="", stderr=""):
    class P:
        pass

    p = P()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


def test_runner_missing_cli(monkeypatch):
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: None)
    res = AgentRunner().run("hi")
    assert res.ok is False
    assert "not found" in (res.error or "")


def test_runner_success(monkeypatch):
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    runner = AgentRunner(runner=lambda *a, **k: _fake_proc(0, "done"))
    res = runner.run("prompt")
    assert res.ok is True
    assert res.output == "done"


def test_runner_nonzero(monkeypatch):
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    runner = AgentRunner(runner=lambda *a, **k: _fake_proc(1, "", "bad"))
    res = runner.run("prompt")
    assert res.ok is False
    assert res.error == "bad"


def test_runner_timeout(monkeypatch):
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    res = AgentRunner(runner=boom, timeout=1).run("p")
    assert res.ok is False
    assert "timed out" in (res.error or "")


def test_write_artifact(tmp_path):
    out = write_artifact(tmp_path / "sub" / "a.md", "content")
    assert out.exists()
    assert out.read_text() == "content"
