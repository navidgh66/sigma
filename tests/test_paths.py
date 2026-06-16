from datetime import date

from cli.paths import DOMAINS, slugify, spec_workspace, specs_dir


def test_domains_count():
    assert len(DOMAINS) == 9
    assert "nlp" in DOMAINS and "rl" in DOMAINS


def test_slugify_basic():
    assert slugify("User Profile Settings!") == "user-profile-settings"
    assert slugify("  Multiple   spaces  ") == "multiple-spaces"
    assert slugify("Already-slug") == "already-slug"


def test_slugify_empty_fallback():
    assert slugify("!!!") == "untitled"
    assert slugify("") == "untitled"


def test_spec_workspace_shape(tmp_path):
    ws = spec_workspace("My Topic", root=tmp_path, today=date(2026, 6, 16))
    assert ws.name == "2026-06-16-my-topic"
    assert ws.parent == specs_dir(tmp_path)
