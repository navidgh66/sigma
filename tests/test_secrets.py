"""Tests for cli.secrets — ~/.sigma/.env key store (never the committed config)."""

from __future__ import annotations

import stat

from cli import secrets


def test_env_path_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    assert secrets.env_path() == tmp_path / ".env"


def test_write_key_creates_file_chmod_600(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    secrets.write_key("GEMINI_API_KEY", "abc123")
    f = secrets.env_path()
    assert f.exists()
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode == 0o600  # owner read/write only


def test_read_env_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    secrets.write_key("GEMINI_API_KEY", "abc123")
    secrets.write_key("OPENAI_API_KEY", "xyz789")
    env = secrets.read_env()
    assert env["GEMINI_API_KEY"] == "abc123"
    assert env["OPENAI_API_KEY"] == "xyz789"


def test_write_key_updates_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    secrets.write_key("GEMINI_API_KEY", "old")
    secrets.write_key("GEMINI_API_KEY", "new")
    assert secrets.read_env()["GEMINI_API_KEY"] == "new"
    # no duplicate lines
    assert secrets.env_path().read_text().count("GEMINI_API_KEY") == 1


def test_write_key_preserves_other_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    secrets.write_key("GEMINI_API_KEY", "g")
    secrets.write_key("OPENAI_API_KEY", "o")
    secrets.write_key("GEMINI_API_KEY", "g2")
    env = secrets.read_env()
    assert env["OPENAI_API_KEY"] == "o"
    assert env["GEMINI_API_KEY"] == "g2"


def test_read_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    assert secrets.read_env() == {}


def test_read_chmod_600_preserved_on_update(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    secrets.write_key("GEMINI_API_KEY", "a")
    secrets.write_key("OPENAI_API_KEY", "b")
    mode = stat.S_IMODE(secrets.env_path().stat().st_mode)
    assert mode == 0o600


def test_known_keys_defined():
    assert "GEMINI_API_KEY" in secrets.KNOWN_KEYS
    assert "OPENAI_API_KEY" in secrets.KNOWN_KEYS


def test_firecrawl_key_is_known():
    assert "FIRECRAWL_API_KEY" in secrets.KNOWN_KEYS


def test_missing_keys_reports_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    missing = secrets.missing_keys()
    assert set(missing) == set(secrets.KNOWN_KEYS)


def test_present_key_not_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    secrets.write_key("GEMINI_API_KEY", "present")
    missing = secrets.missing_keys()
    assert "GEMINI_API_KEY" not in missing
    assert "OPENAI_API_KEY" in missing


def test_env_var_counts_as_present(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMA_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    missing = secrets.missing_keys()
    assert "OPENAI_API_KEY" not in missing  # ambient env satisfies it
