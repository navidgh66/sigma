"""caveman was removed in 0.29.0: sigma neither installs nor checks it."""

import importlib.util
import inspect
from pathlib import Path

from cli import checks, onboard

ROOT = Path(__file__).resolve().parent.parent


def _without_changelog(text: str) -> str:
    """Drop README's "What's new" block: it may name removed features by design."""
    start = text.find("## 🆕 What's new")
    if start == -1:
        return text
    end = text.find("\n---", start)
    return text[:start] + (text[end:] if end != -1 else "")


def test_no_caveman_module_or_vendored_skill():
    assert importlib.util.find_spec("cli.caveman") is None
    assert not (ROOT / "skills" / "vendor" / "caveman").exists()


def test_doctor_and_onboard_do_not_touch_caveman():
    assert not hasattr(checks, "check_caveman")
    assert "caveman_status_fn" not in inspect.signature(checks.run_all).parameters
    assert "caveman_status_fn" not in inspect.signature(onboard.run_onboard).parameters


def test_no_caveman_mentions_in_shipped_surfaces():
    surfaces = [*ROOT.glob("cli/*.py"), *ROOT.glob("commands/*.md"),
                *ROOT.glob("skills/sigma-*/SKILL.md"), ROOT / "skills" / "vendor" / "README.md",
                ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "ARCHITECTURE.md",
                ROOT / "docs" / "PLAYGROUND.md", ROOT / "installer" / "setup.sh"]
    for f in surfaces:
        assert "caveman" not in _without_changelog(f.read_text()).lower(), f.relative_to(ROOT)
