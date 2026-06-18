"""Tests for cli.render — logo + check output (rich with a plain fallback)."""

from __future__ import annotations

from cli import render
from cli.checks import FAIL, OK, WARN, Check


def test_logo_contains_sigma_mark():
    logo = render.logo()
    assert "σ" in logo or "sigma" in logo.lower()


def test_print_logo_smoke(capsys):
    render.print_logo(use_rich=False)
    out = capsys.readouterr().out
    assert out.strip()


def test_print_checks_plain_shows_all(capsys):
    checks = [
        Check("python", OK, "Python 3.11"),
        Check("rtk", WARN, "not installed"),
        Check("deps", FAIL, "missing rich"),
    ]
    render.print_checks(checks, use_rich=False)
    out = capsys.readouterr().out
    assert "python" in out
    assert "rtk" in out
    assert "deps" in out


def test_print_checks_marks_status(capsys):
    render.print_checks([Check("x", OK, "fine"), Check("y", FAIL, "bad")], use_rich=False)
    out = capsys.readouterr().out
    # ok and fail should render distinct glyphs
    assert "✓" in out
    assert "✗" in out


def test_confirm_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert render.confirm("do it?") is True


def test_confirm_no_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert render.confirm("do it?") is False  # default no


def test_confirm_explicit_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert render.confirm("do it?") is False


def test_summary_counts():
    checks = [Check("a", OK, ""), Check("b", OK, ""), Check("c", WARN, ""), Check("d", FAIL, "")]
    counts = render.summarize(checks)
    assert counts[OK] == 2
    assert counts[WARN] == 1
    assert counts[FAIL] == 1
