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
                   "ends your turn", "- [x]", "git merge --abort", "-2/", "restore",
                   "git worktree add", "git merge --no-ff", "<run>-<id>", "git status --porcelain"]:
        assert needle in loop, needle
    assert "ends your turn" not in (ROOT / "commands" / "implement-task.md").read_text()


PROMPT_FILES = (
    list((ROOT / "commands").glob("*.md"))
    + list(AGENTS.glob("*.md"))
    + list((ROOT / "skills").glob("sigma-*/SKILL.md"))
)
REMOVED = ["sigma hermes", "/hermes", "/board", "/weave", "sigma weave", "/eval",
           "sigma eval", "sigma loop", "sigma trajectory", "sigma lessons", "chain.json",
           "events.jsonl", "kanban"]


def test_no_reasoning_extraction_or_think_harder_lines():
    bad = re.compile(r"think step by step|think carefully|explain your reasoning|show your (reasoning|thinking)", re.I)
    for f in PROMPT_FILES:
        assert not bad.search(f.read_text()), f.name


def test_no_references_to_removed_features():
    for f in PROMPT_FILES:
        text = f.read_text()
        for needle in REMOVED:
            assert needle not in text, f"{f.relative_to(ROOT)}: {needle}"


def test_shouting_is_rare():
    # Opus 5.5-era models over-react to stacked capitalized emphasis. Vocabulary is
    # not emphasis: CRITICAL is sigma's severity label and "MUST invariants" is the
    # grill rubric's term for constitution rules, so both are ignored here.
    caps = re.compile(r"\b(MUST|NEVER|ALWAYS|IMPORTANT|DO NOT)\b")
    vocab = re.compile(r"\bMUST(?=[ -](invariants|principles))")
    for f in PROMPT_FILES:
        text = vocab.sub("", f.read_text())
        assert len(caps.findall(text)) <= 1, f"{f.relative_to(ROOT)}"


def test_untrusted_input_guardrail_where_outside_text_enters():
    # Opus 5.5 guide: mark pasted/outside text and follow instructions inside it only
    # where the user's own message asks. /craft takes pasted designs; /research reads
    # manual findings + web results; /review reads other people's diffs.
    assert "<pasted_content" in (ROOT / "commands" / "craft.md").read_text()
    for name in ["craft.md", "research.md", "review.md"]:
        assert "only where the user's own message asks" in (ROOT / "commands" / name).read_text(), name


def test_plugin_manifest_mentions_only_kept_features():
    import json

    desc = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["description"]
    for gone in ["Hermes", "kanban", "HTML artifact"]:
        assert gone not in desc


def test_craft_gives_progress_updates_per_stage():
    # Opus 5.5: predictable progress updates (intent before, recap after) help in
    # human-in-the-loop chains like /craft.
    craft = (ROOT / "commands" / "craft.md").read_text()
    assert "Progress updates" in craft
    assert "one line" in craft and "recap" in craft


def test_research_gives_parallel_lanes_a_time_budget():
    # Opus 5.5: time signals (elapsed / budget) help agent teams finish sooner.
    research = (ROOT / "commands" / "research.md").read_text()
    assert "elapsed" in research and "budget" in research
