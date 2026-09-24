"""End-to-end: onboard then doctor, wired together with injected I/O."""

from __future__ import annotations


# --------------------------- doctor + onboard E2E --------------------------- #
def test_onboard_then_doctor_clean(tmp_path, monkeypatch):
    """Onboard writes config + key; a follow-up doctor --check sees them healthy."""
    from cli import doctor, onboard, secrets

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Run onboard with everything injected — choose nlp, store one key, skip rtk.
    onboard.run_onboard(
        name="e2e",
        domain_input=lambda: "3",
        secret_input=lambda key: "gkey" if key == "GEMINI_API_KEY" else "",
        confirm=lambda msg: False,
        rtk_status_fn=lambda: {"installed": False, "hook_active": False, "gain_ok": False},
        spawn=lambda argv: 0,
        run_all=lambda **k: [],
        which=lambda n: None,
        use_rich=False,
        domains=["classic-ml", "deep-learning", "nlp", "rl"],
    )

    # Secret landed in ~/.sigma/.env, not the committed config.
    assert secrets.read_env().get("GEMINI_API_KEY") == "gkey"
    assert "gkey" not in (tmp_path / "sigma.config.yml").read_text()

    # doctor --check honours statuses: config OK + secrets WARN → exit 0
    # (warnings never fail the gate; only FAILs do). Full probe set is covered
    # in test_checks — here we assert the doctor wiring.
    from cli.checks import OK, WARN, Check

    rc = doctor.run_doctor(
        check_only=True,
        run_all=lambda: [Check("config", OK, "valid"), Check("secrets", WARN, "partial")],
        use_rich=False,
    )
    assert rc == 0
