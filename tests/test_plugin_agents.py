"""Plugin surface checks: role agents, loop command, Opus 5.5 prompt rules."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
EXPECTED = {
    "sigma-implementer": "medium",
    "sigma-verifier": "medium",
    "sigma-test-writer": "low",
    "sigma-e2e": "low",
}


def _front(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path.name}: missing frontmatter"
    return yaml.safe_load(m.group(1))


def test_agents_have_expected_frontmatter():
    for name, effort in EXPECTED.items():
        fm = _front(AGENTS / f"{name}.md")
        assert fm["name"] == name
        assert fm["description"].strip()
        assert fm["effort"] == effort


def test_verifier_cannot_edit():
    tools = {t.strip() for t in _front(AGENTS / "sigma-verifier.md")["tools"].split(",")}
    assert "Bash" in tools and "Read" in tools
    assert not tools & {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def test_e2e_cannot_edit():
    tools = {t.strip() for t in _front(AGENTS / "sigma-e2e.md")["tools"].split(",")}
    assert not tools & {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def test_loop_command_wires_guards_and_unattended_paragraph():
    loop = (ROOT / "commands" / "loop.md").read_text()
    for needle in ["loop-state.json", "test_guard.py", "--root <root>", "sigma-implementer",
                   "sigma-verifier", "sigma-e2e", "sigma-test-writer", "blocker",
                   "ends your turn", "- [x]", "merged back", "-2/"]:
        assert needle in loop, needle
    assert "ends your turn" not in (ROOT / "commands" / "implement-task.md").read_text()
