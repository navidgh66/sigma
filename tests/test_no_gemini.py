"""gemini was removed in 0.30.0: research runs on claude + codex (gpt) only."""

from pathlib import Path

from cli import checks, config, models, secrets

ROOT = Path(__file__).resolve().parent.parent


def test_no_gemini_adapter_default_or_key():
    assert "gemini" not in models.ADAPTERS
    assert config.DEFAULT_MODELS == ["claude", "gpt"]
    assert "GEMINI_API_KEY" not in secrets.KNOWN_KEYS
    assert "gemini" not in checks._MODEL_EXES


def test_legacy_config_listing_gemini_still_loads(tmp_path):
    # Existing sigma.config.yml files may still list gemini: drop it quietly.
    (tmp_path / "sigma.config.yml").write_text(
        "research:\n  models:\n  - claude\n  - gemini\n  - gpt\ndomains:\n- nlp\n"
    )
    cfg = config.load_config(root=tmp_path)
    assert cfg.models == ["claude", "gpt"]
    assert cfg.validate() == []


def test_no_gemini_mentions_in_shipped_surfaces():
    surfaces = [*ROOT.glob("cli/*.py"), *ROOT.glob("commands/*.md"), *ROOT.glob("agents/*.md"),
                *ROOT.glob("skills/sigma-*/SKILL.md"), *ROOT.glob("subagents/**/*.md"),
                *ROOT.glob("scripts/*.py"), ROOT / "sigma.config.yml",
                ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "ARCHITECTURE.md",
                ROOT / "docs" / "PLAYGROUND.md", ROOT / "installer" / "setup.sh",
                ROOT / ".claude-plugin" / "plugin.json"]
    for f in surfaces:
        text = f.read_text().lower()
        if f.name == "config.py":
            text = text.replace('_retired_models = {"gemini"}', "")  # the one allowed mention
        assert "gemini" not in text, f.relative_to(ROOT)
