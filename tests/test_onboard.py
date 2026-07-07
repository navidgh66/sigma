"""Tests for cli.onboard — interactive first-run setup (all inputs injected)."""

from __future__ import annotations

from cli import onboard, secrets
from cli.config import load_config


def _io(answers):
    """Build an injectable input() that pops scripted answers."""
    queue = list(answers)
    return lambda prompt="": queue.pop(0) if queue else ""


# --------------------------- domain/model selection --------------------------- #
def test_select_domains_by_numbers():
    chosen = onboard.parse_domain_selection("1,3", ["nlp", "rl", "mlops"])
    assert chosen == ["nlp", "mlops"]


def test_select_domains_all_on_empty():
    chosen = onboard.parse_domain_selection("", ["nlp", "rl"])
    assert chosen == ["nlp", "rl"]


def test_select_domains_ignores_bad_index():
    chosen = onboard.parse_domain_selection("1,99,abc", ["nlp", "rl"])
    assert chosen == ["nlp"]


# --------------------------- config write --------------------------- #
def test_onboard_writes_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    onboard.run_onboard(
        name="proj",
        domain_input=lambda: "1,2",
        secret_input=lambda key: "",          # skip secrets
        confirm=lambda msg: False,            # skip rtk
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp", "rl", "mlops"],
    )
    cfg = load_config(root=tmp_path)
    assert cfg.domains == ["nlp", "rl"]


# --------------------------- secrets capture --------------------------- #
def test_onboard_captures_secret_to_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provided = {"GEMINI_API_KEY": "secret-g", "OPENAI_API_KEY": ""}
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: provided.get(key, ""),
        confirm=lambda msg: False,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    env = secrets.read_env()
    assert env.get("GEMINI_API_KEY") == "secret-g"
    assert "OPENAI_API_KEY" not in env  # blank skipped


def test_onboard_secret_never_in_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "leaky" if key == "GEMINI_API_KEY" else "",
        confirm=lambda msg: False,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    config_text = (tmp_path / "sigma.config.yml").read_text()
    assert "leaky" not in config_text  # secret must never hit the committed config


# --------------------------- rtk --------------------------- #
def test_onboard_sets_up_rtk_on_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: True,                     # yes to rtk
        learn_fn=lambda root: None,                   # don't spawn a real learn agent
        rtk_status_fn=lambda: {"installed": True, "hook_active": False, "gain_ok": True},
        # caveman + graphify already active → their steps no-op, isolating the rtk assertion.
        caveman_status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        graphify_status_fn=lambda: {"installed": True},
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: "/usr/bin/rtk" if n == "rtk" else None,
        use_rich=False,
        domains=["nlp"],
    )
    assert ["rtk", "init", "-g"] in spawned


# --------------------------- caveman --------------------------- #
def test_onboard_sets_up_caveman_on_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: True,                     # yes to everything
        learn_fn=lambda root: None,                   # don't spawn a real learn agent
        rtk_status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": False, "hook_active": False},
        graphify_status_fn=lambda: {"installed": True},  # already installed → no-op
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    # caveman install ran (marketplace add + plugin install).
    assert any("marketplace" in a for a in spawned)
    assert any("install" in a for a in spawned)


def test_onboard_skips_caveman_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": False, "hook_active": False},
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    assert spawned == []


def test_onboard_skips_rtk_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    assert spawned == []


# --------------------------- graphify --------------------------- #
def test_onboard_installs_graphify_on_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: True,
        learn_fn=lambda root: None,                   # don't spawn a real learn agent
        # rtk + caveman + statusline already satisfied → only graphify acts.
        rtk_status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        statusline_status_fn=lambda: {"node_runtime": True, "configured": True},
        graphify_status_fn=lambda: {"installed": False},
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: "/bin/uv" if n == "uv" else None,
        use_rich=False,
        domains=["nlp"],
    )
    # graphify install ran via uv.
    assert any(a[:3] == ["uv", "tool", "install"] for a in spawned)


def test_onboard_skips_graphify_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        graphify_status_fn=lambda: {"installed": False},
        spawn=lambda argv: spawned.append(argv) or 0,
        run_all=lambda **k: [],
        which=lambda n: "/bin/uv",
        use_rich=False,
        domains=["nlp"],
    )
    assert spawned == []


# --------------------------- graphify post-commit hook --------------------------- #
def test_onboard_installs_graphify_hook(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    spawned = []
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: True,
        learn_fn=lambda root: None,                   # don't spawn a real learn agent
        # rtk + caveman + statusline + graphify install already satisfied → only the
        # hook step acts. graphify binary present + no .git hook in tmp_path → install.
        rtk_status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        statusline_status_fn=lambda: {"node_runtime": True, "configured": True},
        graphify_status_fn=lambda: {"installed": True},   # step 9 install no-ops
        spawn=lambda argv, cwd=None: spawned.append(argv) or 0,
        which=lambda n: "/bin/graphify" if n == "graphify" else None,
        run_all=lambda **k: [],
        use_rich=False,
        domains=["nlp"],
    )
    assert ["graphify", "hook", "install"] in spawned
    assert "graphify post-commit hook installed" in capsys.readouterr().out


# --------------------------- learn artifacts (step 11) --------------------------- #
class _LearnRes:
    def __init__(self, ok=True, error=None):
        self.ok = ok
        self.error = error


def _base_kwargs(tmp_path):
    """Onboard kwargs with every install step satisfied → isolate the learn step."""
    return dict(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        rtk_status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        statusline_status_fn=lambda: {"node_runtime": True, "configured": True},
        graphify_status_fn=lambda: {"installed": True},
        spawn=lambda argv: 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )


def test_onboard_builds_learn_on_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    (tmp_path / "sigma.config.yml").write_text("name: t\n")  # mark project root
    called = []
    onboard.run_onboard(
        confirm=lambda msg: True,
        learn_fn=lambda root: called.append(root) or _LearnRes(ok=True),
        **_base_kwargs(tmp_path),
    )
    assert called, "learn_fn should run when confirmed and no artifacts exist"


def test_onboard_skips_learn_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    (tmp_path / "sigma.config.yml").write_text("name: t\n")
    called = []
    onboard.run_onboard(
        confirm=lambda msg: False,
        learn_fn=lambda root: called.append(root) or _LearnRes(ok=True),
        **_base_kwargs(tmp_path),
    )
    assert called == []


def test_onboard_skips_learn_when_artifacts_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    (tmp_path / "sigma.config.yml").write_text("name: t\n")
    (tmp_path / "ARCHITECTURE.md").write_text("# already here\n")
    called = []
    onboard.run_onboard(
        confirm=lambda msg: True,  # would say yes, but artifacts exist → no-op
        learn_fn=lambda root: called.append(root) or _LearnRes(ok=True),
        **_base_kwargs(tmp_path),
    )
    assert called == [], "must not rebuild when ARCHITECTURE.md already exists"


# --------------------------- session hook --------------------------- #
def test_onboard_adds_session_hook_on_confirm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: True,
        learn_fn=lambda root: None,                   # don't spawn a real learn agent
        # everything else already satisfied → isolate the session-hook step.
        rtk_status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True},
        caveman_status_fn=lambda: {"claude_cli": True, "installed": True, "hook_active": True},
        statusline_status_fn=lambda: {"node_runtime": True, "configured": True},
        graphify_status_fn=lambda: {"installed": True},
        spawn=lambda argv: 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()
    assert "session-context" in settings.read_text()


def test_onboard_skips_session_hook_when_declined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    onboard.run_onboard(
        name="p",
        domain_input=lambda: "",
        secret_input=lambda key: "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        graphify_status_fn=lambda: {"installed": False},
        spawn=lambda argv: 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp"],
    )
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_onboard_idempotent_rerun(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    kwargs = dict(
        name="p",
        domain_input=lambda: "1",
        secret_input=lambda key: "",
        confirm=lambda msg: False,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["nlp", "rl"],
    )
    onboard.run_onboard(**kwargs)
    onboard.run_onboard(**kwargs)  # must not raise
    cfg = load_config(root=tmp_path)
    assert cfg.domains == ["nlp"]
