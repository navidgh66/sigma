from cli.config import (
    DEFAULT_COMMANDS,
    SigmaConfig,
    load_config,
    write_config,
)


def test_default_config_valid():
    cfg = SigmaConfig()
    assert cfg.validate() == []
    assert cfg.commands == DEFAULT_COMMANDS
    assert len(cfg.domains) == 9


def test_unknown_domain_invalid():
    cfg = SigmaConfig(domains=["nlp", "not-a-domain"])
    errors = cfg.validate()
    assert any("unknown domain" in e for e in errors)


def test_empty_domains_invalid():
    cfg = SigmaConfig(domains=[])
    assert any("at least one domain" in e for e in cfg.validate())


def test_loop_worktrees_round_trips_false(tmp_path):
    cfg = SigmaConfig()
    cfg.loop.worktrees = False
    write_config(cfg, root=tmp_path)
    loaded = load_config(root=tmp_path)
    assert loaded.loop.worktrees is False


def test_loop_worktrees_defaults_true(tmp_path):
    cfg = SigmaConfig()
    write_config(cfg, root=tmp_path)
    loaded = load_config(root=tmp_path)
    assert loaded.loop.worktrees is True


def test_bad_max_cycles_invalid():
    cfg = SigmaConfig()
    cfg.loop.max_cycles = 0
    assert any("max_cycles" in e for e in cfg.validate())


def test_write_then_load_roundtrip(tmp_path):
    cfg = SigmaConfig(name="proj-x", domains=["nlp", "rl"], models=["claude"])
    cfg.loop.max_cycles = 5
    write_config(cfg, root=tmp_path)
    loaded = load_config(root=tmp_path)
    assert loaded.name == "proj-x"
    assert loaded.domains == ["nlp", "rl"]
    assert loaded.models == ["claude"]
    assert loaded.loop.max_cycles == 5


def test_local_override_merges(tmp_path):
    cfg = SigmaConfig(name="base", models=["claude", "gemini", "gpt"])
    write_config(cfg, root=tmp_path)
    (tmp_path / "sigma.config.local.yml").write_text(
        "research:\n  models: [claude]\n"
    )
    loaded = load_config(root=tmp_path)
    # local override wins for models, base retained for name
    assert loaded.models == ["claude"]
    assert loaded.name == "base"
