"""Tests for cli.checks — the pure diagnostic probe engine.

Every probe takes injected dependencies (which/env/home) so no real subprocess
runs and nothing on the host is touched.
"""

from __future__ import annotations

from cli import checks
from cli.checks import FAIL, OK, WARN


def _which(present):
    """Build a fake shutil.which that only knows `present` names."""
    return lambda name: f"/usr/bin/{name}" if name in present else None


# --------------------------- Check dataclass --------------------------- #
def test_check_has_status_and_detail():
    c = checks.Check(name="x", status=OK, detail="fine")
    assert c.status == OK
    assert c.fix is None


def test_check_can_carry_fix():
    c = checks.Check(name="x", status=FAIL, detail="bad", fix=("install it", lambda: True))
    assert c.fixable
    assert c.fix[0] == "install it"


# --------------------------- python --------------------------- #
def test_python_ok_on_39_plus():
    c = checks.check_python(version=(3, 9, 0))
    assert c.status == OK


def test_python_fail_below_39():
    c = checks.check_python(version=(3, 8, 0))
    assert c.status == FAIL


# --------------------------- deps --------------------------- #
def test_deps_ok_when_importable():
    c = checks.check_deps(probe=lambda mod: True)
    assert c.status == OK


def test_deps_fail_when_missing():
    c = checks.check_deps(probe=lambda mod: mod != "rich")
    assert c.status == FAIL
    assert c.fixable  # offers pip install


# --------------------------- models --------------------------- #
def test_models_ok_when_any_present():
    c = checks.check_models(which=_which({"claude"}))
    assert c.status in (OK, WARN)
    assert "claude" in c.detail


def test_models_warn_when_none():
    c = checks.check_models(which=_which(set()))
    assert c.status == WARN


# --------------------------- model auth --------------------------- #
def test_model_auth_guidance_when_cli_present():
    c = checks.check_model_auth(which=_which({"gemini"}))
    # present but auth unknown → a guidance command is offered, never auto-run
    assert "gemini" in c.detail


# --------------------------- secrets --------------------------- #
def test_secrets_ok_when_present(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    c = checks.check_secrets()
    assert c.status == OK


def test_secrets_warn_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = checks.check_secrets()
    assert c.status == WARN


# --------------------------- vendored skills --------------------------- #
def test_vendored_skills_ok(tmp_path):
    vendor = tmp_path / "skills" / "vendor" / "caveman"
    vendor.mkdir(parents=True)
    (vendor / "SKILL.md").write_text("x")
    c = checks.check_vendored_skills(home=tmp_path)
    assert c.status == OK


def test_vendored_skills_fail_when_absent(tmp_path):
    c = checks.check_vendored_skills(home=tmp_path)
    assert c.status == FAIL
    assert c.fixable  # offers re-vendor


# --------------------------- plugin --------------------------- #
def test_plugin_ok_when_manifest_valid(tmp_path):
    pdir = tmp_path / ".claude-plugin"
    pdir.mkdir()
    (pdir / "plugin.json").write_text('{"name":"sigma","description":"d"}')
    c = checks.check_plugin(home=tmp_path)
    assert c.status == OK


def test_plugin_fail_on_bad_json(tmp_path):
    pdir = tmp_path / ".claude-plugin"
    pdir.mkdir()
    (pdir / "plugin.json").write_text("{not json")
    c = checks.check_plugin(home=tmp_path)
    assert c.status == FAIL


# --------------------------- config --------------------------- #
def test_config_warn_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = checks.check_config(root=tmp_path)
    assert c.status in (WARN, FAIL)


def test_config_ok_when_valid(tmp_path):
    (tmp_path / "sigma.config.yml").write_text(
        "profile:\n  name: t\ndomains:\n  - nlp\n"
    )
    c = checks.check_config(root=tmp_path)
    assert c.status == OK


def test_config_fail_unknown_domain(tmp_path):
    (tmp_path / "sigma.config.yml").write_text("domains:\n  - bogus\n")
    c = checks.check_config(root=tmp_path)
    assert c.status == FAIL


# --------------------------- workspaces --------------------------- #
def test_workspaces_ok_when_events_parse(tmp_path):
    ws = tmp_path / "sigma" / "specs" / "2026-06-18-demo"
    ws.mkdir(parents=True)
    (ws / "events.jsonl").write_text('{"task":"T1","stage":"spec","status":"done"}\n')
    c = checks.check_workspaces(root=tmp_path)
    assert c.status == OK


def test_workspaces_warn_on_corrupt_events(tmp_path):
    ws = tmp_path / "sigma" / "specs" / "2026-06-18-demo"
    ws.mkdir(parents=True)
    (ws / "events.jsonl").write_text("NOT JSON\n")
    c = checks.check_workspaces(root=tmp_path)
    assert c.status == WARN


# --------------------------- rtk --------------------------- #
def test_rtk_ok_when_installed_and_active():
    c = checks.check_rtk(status_fn=lambda: {"installed": True, "hook_active": True, "gain_ok": True})
    assert c.status == OK


def test_rtk_warn_when_installed_not_active():
    c = checks.check_rtk(status_fn=lambda: {"installed": True, "hook_active": False, "gain_ok": True})
    assert c.status == WARN
    assert c.fixable  # offers rtk init -g


def test_rtk_fail_when_absent():
    c = checks.check_rtk(status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False})
    assert c.status in (WARN, FAIL)
    assert c.fixable  # offers install + activate


# --------------------------- run_all --------------------------- #
def test_run_all_returns_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    out = checks.run_all(home=tmp_path, root=tmp_path, which=_which({"claude"}))
    assert isinstance(out, list)
    assert all(isinstance(c, checks.Check) for c in out)
    names = {c.name for c in out}
    assert "python" in names and "rtk" in names and "secrets" in names
