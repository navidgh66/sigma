"""Domain guidance must reflect current Claude 5 family practice."""

from pathlib import Path

CE = Path(__file__).resolve().parent.parent / "context-engines"


def test_prompt_engineering_no_cot_prompting_and_uses_effort():
    text = (CE / "llm-engineering" / "implementers" / "prompt-engineering.md").read_text()
    assert "Think step by step" not in text
    for needle in ["effort", "reasoning_extraction", "max_tokens", "pasted_content"]:
        assert needle in text, needle


def test_harness_design_has_unattended_run_patterns():
    text = (CE / "ai-agent-engineering" / "implementers" / "harness-design.md").read_text()
    for needle in ["end_turn", "checklist", "continuations", "elapsed", 'display: "updates"']:
        assert needle in text, needle


def test_agent_verifier_flags_end_turn_as_done():
    text = (CE / "ai-agent-engineering" / "verifiers" / "agent-soundness.md").read_text()
    assert "end_turn" in text


def test_llm_verifier_flags_reasoning_in_response():
    text = (CE / "llm-engineering" / "verifiers" / "llm-soundness.md").read_text()
    assert "reasoning_extraction" in text


def test_agent_logic_evaluator_checks_completion_condition():
    text = (CE / "ai-agent-engineering" / "verifiers" / "logic-evaluator.md").read_text()
    assert "completion condition" in text.lower()
