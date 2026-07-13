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


# --------------------------------------------------------------------------- #
# Model routing
# --------------------------------------------------------------------------- #
def test_runner_default_argv_has_no_model(monkeypatch):
    """Default runner (no model) builds the bare `claude -p <prompt>` argv."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    AgentRunner(runner=spy).run("hello")
    assert captured["argv"] == ["claude", "-p", "hello"]


def test_runner_model_injects_flag(monkeypatch):
    """A set model adds `--model <alias>` before the prompt (alias passed through)."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    AgentRunner(runner=spy, model="haiku").run("hello")
    assert captured["argv"] == ["claude", "-p", "--model", "haiku", "hello"]


def test_runner_argv_builder_bypasses_default_argv(monkeypatch):
    """A set argv_builder fully replaces the built-in [-p, --model] argv shape."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/codex")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    def builder(prompt, model):
        return ["codex", "exec", "--sandbox", "read-only", "--color", "never", prompt]

    AgentRunner(executable="codex", runner=spy, argv_builder=builder, model="ignored").run("hello")
    assert captured["argv"] == ["codex", "exec", "--sandbox", "read-only", "--color", "never", "hello"]


def test_runner_no_argv_builder_uses_default(monkeypatch):
    """argv_builder=None (default) is byte-identical to the pre-existing argv shape."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    AgentRunner(runner=spy).run("hello")
    assert captured["argv"] == ["claude", "-p", "hello"]


def test_runner_output_cleaner_applied(monkeypatch):
    """A set output_cleaner post-processes raw stdout before it becomes AgentResult.output."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/codex")
    raw = "workdir: /tmp\nVERDICT: PASS\n"
    runner = AgentRunner(
        executable="codex",
        runner=lambda *a, **k: _fake_proc(0, raw),
        output_cleaner=lambda text: "VERDICT: PASS",
    )
    res = runner.run("p")
    assert res.ok is True
    assert res.output == "VERDICT: PASS"


def test_runner_no_output_cleaner_strips_raw(monkeypatch):
    """output_cleaner=None (default) is byte-identical to today's bare .strip()."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    runner = AgentRunner(runner=lambda *a, **k: _fake_proc(0, "  done  "))
    res = runner.run("p")
    assert res.output == "done"


# --------------------------------------------------------------------------- #
# Trajectory sink
# --------------------------------------------------------------------------- #
def test_runner_calls_trajectory_sink(monkeypatch):
    """When a sink is set, each run emits one step dict to it."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    steps = []
    runner = AgentRunner(
        runner=lambda *a, **k: _fake_proc(0, "done"),
        trajectory_sink=steps.append,
        model="sonnet",
    )
    runner.run("p", role="implementer")
    assert len(steps) == 1
    assert steps[0]["role"] == "implementer"
    assert steps[0]["ok"] is True
    assert steps[0]["model"] == "sonnet"


def test_runner_sink_failure_swallowed(monkeypatch):
    """A broken sink never breaks the run (observability is best-effort)."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")

    def boom(_step):
        raise RuntimeError("sink down")

    res = AgentRunner(
        runner=lambda *a, **k: _fake_proc(0, "done"),
        trajectory_sink=boom,
    ).run("p")
    assert res.ok is True
    assert res.output == "done"


def test_runner_no_sink_no_step(monkeypatch):
    """Without a sink, behavior is byte-identical to before (no-op)."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    res = AgentRunner(runner=lambda *a, **k: _fake_proc(0, "done")).run("p")
    assert res.ok is True


# --------------------------- telemetry (real token usage) --------------------

def _telemetry_proc(stdout, returncode=0, stderr=""):
    class P:
        pass
    p = P()
    p.stdout = stdout
    p.returncode = returncode
    p.stderr = stderr
    return p


def test_telemetry_argv_requests_json_output(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _telemetry_proc('{"result": "hi", "usage": {"input_tokens": 1, "output_tokens": 2}}')

    r = AgentRunner(runner=fake_run, telemetry=True)
    monkeypatch.setattr(r, "available", lambda: True)
    r.run("prompt")
    assert "--output-format" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--output-format") + 1] == "json"
    assert seen["argv"][-1] == "prompt"


def test_no_telemetry_argv_unchanged(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _telemetry_proc("plain")

    r = AgentRunner(runner=fake_run)
    monkeypatch.setattr(r, "available", lambda: True)
    r.run("prompt")
    assert "--output-format" not in seen["argv"]


def test_telemetry_parses_envelope_text_and_emits_usage(monkeypatch):
    steps = []
    envelope = ('{"result": "VERDICT: PASS", "total_cost_usd": 0.05, '
                '"usage": {"input_tokens": 100, "output_tokens": 40, '
                '"cache_read_input_tokens": 300, "cache_creation_input_tokens": 10}}')

    r = AgentRunner(runner=lambda argv, **kw: _telemetry_proc(envelope),
                    telemetry=True, trajectory_sink=steps.append)
    monkeypatch.setattr(r, "available", lambda: True)
    result = r.run("prompt", role="verifier")
    assert result.ok
    assert result.output == "VERDICT: PASS"
    step = steps[0]
    assert step["input_tokens"] == 100
    assert step["output_tokens"] == 40
    assert step["cache_read_tokens"] == 300
    assert step["cache_creation_tokens"] == 10
    assert step["cost_usd"] == 0.05


def test_telemetry_degrades_to_raw_text_on_unparseable_stdout(monkeypatch):
    steps = []
    r = AgentRunner(runner=lambda argv, **kw: _telemetry_proc("  not json at all  "),
                    telemetry=True, trajectory_sink=steps.append)
    monkeypatch.setattr(r, "available", lambda: True)
    result = r.run("prompt")
    assert result.ok
    assert result.output == "not json at all"
    assert "input_tokens" not in steps[0]  # no fabricated usage


def test_telemetry_ignored_when_argv_builder_set(monkeypatch):
    # codex-shaped runners own their argv + output; telemetry must not touch them.
    seen = {}

    def build(prompt, model):
        return ["codex", "exec", prompt]

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return _telemetry_proc('{"result": "x"}')

    r = AgentRunner(runner=fake_run, telemetry=True, argv_builder=build)
    monkeypatch.setattr(r, "available", lambda: True)
    result = r.run("prompt")
    assert "--output-format" not in seen["argv"]
    assert result.output == '{"result": "x"}'
