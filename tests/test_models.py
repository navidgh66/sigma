import subprocess

from cli.models import (
    ADAPTERS,
    DEEP_TIMEOUT,
    QUICK_TIMEOUT,
    available_models,
    clean_output,
    run_model,
)


def test_adapter_argv_no_shell_injection():
    adapter = ADAPTERS["claude"]
    argv = adapter.build_argv("hello; rm -rf /")
    # The dangerous string stays a single argv element — never shell-split.
    assert argv[0] == "claude"
    assert "hello; rm -rf /" in argv


def test_gpt_adapter_uses_codex_exec():
    # GPT is driven via the subscription-backed Codex CLI, not the dead openai CLI.
    adapter = ADAPTERS["gpt"]
    assert adapter.executable == "codex"
    argv = adapter.build_argv("topic")
    assert argv[:2] == ["codex", "exec"]
    assert "--sandbox" in argv and "read-only" in argv


def test_deep_args_appended_only_when_deep():
    adapter = ADAPTERS["gpt"]
    quick = adapter.build_argv("t", deep=False)
    deep = adapter.build_argv("t", deep=True)
    assert "tools.web_search=true" not in quick
    assert "-c" in deep and "tools.web_search=true" in deep


def test_gpt_adapter_sandbox_param_defaults_read_only():
    """Default sandbox is unchanged — byte-identical to pre-existing behavior."""
    adapter = ADAPTERS["gpt"]
    argv = adapter.build_argv("topic")
    assert "--sandbox" in argv and "read-only" in argv


def test_gpt_adapter_sandbox_param_overridable():
    adapter = ADAPTERS["gpt"]
    argv = adapter.build_argv("topic", sandbox="workspace-write")
    idx = argv.index("--sandbox")
    assert argv[idx + 1] == "workspace-write"
    assert "read-only" not in argv


def test_clean_output_claude_passthrough():
    assert clean_output("claude", "  findings  ") == "findings"


def test_clean_output_codex_strips_metadata():
    raw = (
        "workdir: /tmp/x\n"
        "model: gpt-5\n"
        "[2026-06-18T00:00:00] thinking...\n"
        "Real finding: X causes Y.\n"
        "tokens used: 123\n"
    )
    cleaned = clean_output("gpt", raw)
    assert "Real finding: X causes Y." in cleaned
    assert "workdir" not in cleaned
    assert "tokens used" not in cleaned
    assert "thinking" not in cleaned


def test_clean_output_codex_empty_returns_empty():
    assert clean_output("gpt", "   ") == ""


def test_available_models_filters_missing(monkeypatch):
    import cli.models as m

    def fake_which(exe):
        return "/usr/bin/" + exe if exe == "claude" else None

    monkeypatch.setattr(m.shutil, "which", fake_which)
    assert available_models(["claude", "unknown-model", "gpt"]) == ["claude"]


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


def test_run_model_deep_uses_deep_timeout_and_args(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: "/bin/" + exe)
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = "deep findings"
        stderr = ""

    def fake_runner(argv, **kwargs):
        captured["argv"] = argv
        captured["timeout"] = kwargs.get("timeout")
        return FakeProc()

    res = run_model("gpt", "prompt", deep=True, runner=fake_runner)
    assert res.ok is True
    assert captured["timeout"] == DEEP_TIMEOUT
    assert "tools.web_search=true" in captured["argv"]


def test_run_model_quick_default_timeout(monkeypatch):
    import cli.models as m

    monkeypatch.setattr(m.shutil, "which", lambda exe: "/bin/" + exe)
    captured = {}

    class FakeProc:
        returncode = 0
        stdout = "x"
        stderr = ""

    def fake_runner(argv, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return FakeProc()

    run_model("claude", "prompt", runner=fake_runner)
    assert captured["timeout"] == QUICK_TIMEOUT


def test_build_argv_claude_injects_model_alias():
    argv = ADAPTERS["claude"].build_argv("hello", model_alias="opus")
    assert argv[:3] == ["claude", "--model", "opus"]
    assert argv[-2:] == ["-p", "hello"]


def test_build_argv_without_alias_is_unchanged():
    assert ADAPTERS["claude"].build_argv("hello") == ["claude", "-p", "hello"]


def test_build_argv_gpt_ignores_model_alias():
    # codex has no alias-passthrough --model contract: the alias is dropped,
    # argv unchanged.
    assert ADAPTERS["gpt"].build_argv("hi", model_alias="opus") == ADAPTERS["gpt"].build_argv("hi")
