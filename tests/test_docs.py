"""Doc surfaces stay lean and current."""

import json
from pathlib import Path

from cli import __version__

ROOT = Path(__file__).resolve().parent.parent
REMOVED_CLI = ["sigma hermes", "sigma board", "sigma weave", "sigma eval",
               "sigma trajectory", "sigma lessons", "sigma loop", "sigma launch"]


def test_claude_md_under_200_lines():
    assert len((ROOT / "CLAUDE.md").read_text().splitlines()) < 200


def test_version_parity_and_release():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert __version__ == plugin["version"] == "0.29.0"
    assert market["plugins"][0]["version"] == market["metadata"]["version"] == __version__


def test_docs_do_not_advertise_removed_commands():
    for rel in ["README.md", "CLAUDE.md", "docs/PLAYGROUND.md", "ARCHITECTURE.md"]:
        text = (ROOT / rel).read_text()
        for gone in REMOVED_CLI:
            assert gone not in text, f"{rel}: {gone}"
