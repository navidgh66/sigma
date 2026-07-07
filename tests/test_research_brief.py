from cli.research_brief import QUICK_BRIEF, RULES_TEXT, build_prompt


def test_build_prompt_contains_topic():
    p = build_prompt("graph neural nets")
    assert "graph neural nets" in p
    assert "source" in p.lower()


def test_build_prompt_deep_demands_web_search():
    quick = build_prompt("t", deep=False)
    deep = build_prompt("t", deep=True)
    assert "web-search" in deep or "web search" in deep.lower()
    assert "do NOT answer from memory" in deep
    assert "do NOT answer from memory" not in quick


def test_build_prompt_web_demands_search_but_lighter():
    web = build_prompt("t", web=True)
    quick = build_prompt("t", deep=False)
    assert "search the web" in web.lower()
    assert "QUICK" in web or "quick" in web
    assert web != quick


def test_build_prompt_deep_wins_over_web():
    both = build_prompt("t", deep=True, web=True)
    deep = build_prompt("t", deep=True)
    assert both == deep


def test_rules_text_is_nonempty_and_shared():
    # DEEP_BRIEF/WEB_BRIEF inline their own brief-specific requirement lists
    # (verbatim from the original cli/research.py strings) — they are not
    # byte-identical to RULES_TEXT. Only QUICK_BRIEF composes RULES_TEXT
    # verbatim, since its rules text is reused byte-for-byte as the shared
    # "Return:" bullet list. See cli/research_brief.py module docstring.
    assert "source" in RULES_TEXT.lower()
    assert "confidence" in RULES_TEXT.lower()
    assert RULES_TEXT in QUICK_BRIEF
