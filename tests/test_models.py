import subprocess

from cli.models import (
    ADAPTERS,
    available_models,
    run_model,
)


def test_adapter_argv_no_shell_injection():
    adapter = ADAPTERS["claude"]
    argv = adapter.build_argv("hello; rm -rf /")
    # The dangerous string stays a single argv element — never shell-split.
    assert argv[0] == "claude"
    assert "hello; rm -rf /" in argv


def test_gpt_adapter_uses_openai_executable():
    assert ADAPTERS["gpt"].executable == "openai"


def test_available_models_filters_missing(monkeypatch):
    import cli.models as m

    def fake_which(exe):
        return "/usr/bin/" + exe if exe == "claude" else None

    monkeypatch.setattr(m.shutil, "which", fake_which)
    assert available_models(["claude", "gemini", "gpt"]) == ["claude"]


def test_run_model_unknown():
    res = run_model("nope", "prompt")
    assert res.skipped is True
    assert res.ok is False


def test_run_model_missing_cli(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: None)
    res = run_model("claude", "prompt")
    assert res.skipped is True
    assert "not installed" in (res.error or "")


def test_run_model_success(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: "/bin/" + exe)

    class FakeProc:
        returncode = 0
        stdout = "findings here"
        stderr = ""

    def fake_runner(argv, **kwargs):
        return FakeProc()

    res = run_model("claude", "prompt", runner=fake_runner)
    assert res.ok is True
    assert res.text == "findings here"


def test_run_model_nonzero_exit(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: "/bin/" + exe)

    class FakeProc:
        returncode = 2
        stdout = ""
        stderr = "boom"

    res = run_model("claude", "prompt", runner=lambda *a, **k: FakeProc())
    assert res.ok is False
    assert res.error == "boom"


def test_run_model_timeout(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: "/bin/" + exe)

    def fake_runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

    res = run_model("claude", "prompt", runner=fake_runner, timeout=1)
    assert res.ok is False
    assert "timed out" in (res.error or "")
