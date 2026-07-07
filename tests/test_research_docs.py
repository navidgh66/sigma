from cli.research_brief import RULES_TEXT
from cli.research_docs import render_command_rules_block, render_persona_rules_block


def test_render_command_rules_block_contains_shared_rules():
    block = render_command_rules_block()
    assert "cite" in block.lower() or "source" in block.lower()
    assert "confidence" in block.lower()


def test_render_persona_rules_block_contains_shared_rules():
    block = render_persona_rules_block()
    assert "confidence" in block.lower()
    assert "single-source" in block.lower()


def test_both_blocks_derive_from_the_same_rules_text():
    # Both generated blocks must be textually traceable to RULES_TEXT bullets —
    # not byte-identical (different markdown headers), but every bullet phrase
    # in RULES_TEXT appears in both.
    bullets = [line.strip("- ").split("(")[0].strip() for line in RULES_TEXT.splitlines()]
    cmd_block = render_command_rules_block()
    persona_block = render_persona_rules_block()
    for bullet in bullets:
        key_phrase = bullet.split(",")[0][:20]  # a short distinguishing fragment
        assert key_phrase.lower() in cmd_block.lower()
        assert key_phrase.lower() in persona_block.lower()
