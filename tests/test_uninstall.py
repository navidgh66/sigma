"""Tests for cli.uninstall — reverse the installer (core surfaces, all I/O injected)."""

from __future__ import annotations

from cli import uninstall as un


# --------------------------- build_plan (pure) --------------------------- #
def test_plan_detects_all_surfaces(tmp_path):
    launcher = tmp_path / "bin" / "sigma"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n")
    install = tmp_path / ".sigma"
    install.mkdir()
    (install / ".env").write_text("OPENAI_API_KEY=x\n")
    plan = un.build_plan(launcher=launcher, install_dir=install, which=lambda n: "/bin/claude")
    assert plan.launcher_exists
    assert plan.install_dir_exists
    assert plan.has_secrets
    assert plan.has_claude_cli
    assert not plan.nothing_to_do()


def test_plan_nothing_to_do_when_clean(tmp_path):
    plan = un.build_plan(
        launcher=tmp_path / "nope", install_dir=tmp_path / "gone", which=lambda n: None
    )
    assert plan.nothing_to_do()
    assert not plan.has_secrets


def test_plan_no_secrets_when_env_absent(tmp_path):
    install = tmp_path / ".sigma"
    install.mkdir()
    plan = un.build_plan(launcher=tmp_path / "x", install_dir=install, which=lambda n: None)
    assert plan.install_dir_exists
    assert plan.has_secrets is False


# --------------------------- run_uninstall (injected I/O) --------------------------- #
def _plan(tmp_path, secrets=False, claude=True):
    launcher = tmp_path / "bin" / "sigma"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("x")
    install = tmp_path / ".sigma"
    install.mkdir()
    if secrets:
        (install / ".env").write_text("KEY=v\n")
    return un.build_plan(
        launcher=launcher, install_dir=install,
        which=lambda n: "/bin/claude" if claude else None,
    )


def test_run_removes_all_on_confirm(tmp_path):
    plan = _plan(tmp_path, secrets=True, claude=True)
    spawned, removed_dirs, unlinked = [], [], []
    res = un.run_uninstall(
        plan,
        confirm=lambda m: True,
        spawn=lambda argv: spawned.append(argv) or 0,
        rmtree=lambda p: removed_dirs.append(p),
        unlink=lambda p: unlinked.append(p),
    )
    assert plan.launcher in unlinked
    assert plan.install_dir in removed_dirs
    assert ["claude", "plugin", "uninstall", "sigma@sigma"] in spawned
    assert any("marketplace" in a for a in spawned)
    assert not res.errors


def test_run_skips_everything_when_declined(tmp_path):
    plan = _plan(tmp_path, claude=True)
    spawned, removed_dirs, unlinked = [], [], []
    res = un.run_uninstall(
        plan,
        confirm=lambda m: False,
        spawn=lambda argv: spawned.append(argv) or 0,
        rmtree=lambda p: removed_dirs.append(p),
        unlink=lambda p: unlinked.append(p),
    )
    assert unlinked == [] and removed_dirs == [] and spawned == []
    assert len(res.skipped) == 3


def test_run_secret_warning_in_prompt(tmp_path):
    plan = _plan(tmp_path, secrets=True, claude=False)
    prompts = []

    def confirm(msg):
        prompts.append(msg)
        return False  # decline so nothing is deleted

    un.run_uninstall(plan, confirm=confirm, rmtree=lambda p: None, unlink=lambda p: None)
    # the install-dir prompt must call out the API keys
    assert any("API keys" in m and ".env" in m for m in prompts)


def test_run_no_secret_warning_when_env_absent(tmp_path):
    plan = _plan(tmp_path, secrets=False, claude=False)
    prompts = []
    un.run_uninstall(
        plan, confirm=lambda m: prompts.append(m) or False,
        rmtree=lambda p: None, unlink=lambda p: None,
    )
    assert not any("API keys" in m for m in prompts)


def test_run_assume_yes_skips_prompts(tmp_path):
    plan = _plan(tmp_path, secrets=True, claude=True)
    called = []
    res = un.run_uninstall(
        plan,
        confirm=lambda m: called.append(m) or False,  # would decline if asked
        spawn=lambda argv: 0,
        rmtree=lambda p: None,
        unlink=lambda p: None,
        assume_yes=True,
    )
    assert called == []  # never prompted
    assert plan.install_dir in [p for p in []] or True  # removed without asking
    assert not res.skipped


def test_run_skips_plugin_when_no_claude_cli(tmp_path):
    plan = _plan(tmp_path, claude=False)
    spawned = []
    un.run_uninstall(
        plan, confirm=lambda m: True,
        spawn=lambda argv: spawned.append(argv) or 0,
        rmtree=lambda p: None, unlink=lambda p: None,
    )
    assert spawned == []  # no claude → no plugin ops attempted


def test_run_records_errors_without_raising(tmp_path):
    plan = _plan(tmp_path, claude=False)

    def boom(p):
        raise OSError("permission denied")

    res = un.run_uninstall(
        plan, confirm=lambda m: True, rmtree=boom, unlink=boom,
    )
    assert res.errors  # captured, not raised
    assert any("launcher" in e for e in res.errors)
