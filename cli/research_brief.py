"""Canonical research-brief templates and shared citation/confidence rules.

Single source of truth for the CLI research briefs (cli/research.py) and the
generated docs (cli/research_docs.py → commands/research.md + persona files).
Editing a rule here and regenerating (scripts/regen_research_docs.py) is the
only way rules should change — never hand-edit the generated blocks directly.
"""

from __future__ import annotations

RULES_TEXT = """- Themed findings, each with a source URL
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions"""

QUICK_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Investigate this topic and return raw findings (data for aggregation, not a
human-facing reply):

TOPIC: {{topic}}

Return:
{rules}
""".format(rules=RULES_TEXT)

DEEP_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Use your web-search / grounding tools to investigate this topic against LIVE
sources, then return raw findings (data for aggregation, not a human-facing reply):

TOPIC: {topic}

Requirements:
- Actively search the web; do NOT answer from memory alone
- Themed findings, each with a real, resolvable source URL you actually consulted
- A confidence note per theme (high/medium/low)
- Explicitly flag single-source or unverified claims
- Strongly prefer sources from the last 12 months
- Separate fact from inference; no unsourced assertions
"""

WEB_BRIEF = """You are a research subagent for the 'sigma' toolkit.

Do a QUICK web-grounded check on this topic — search the web for current facts,
but keep it concise (this is the light web pass, not an exhaustive deep dive):

TOPIC: {topic}

Requirements:
- Search the web for recent facts; do not answer from memory alone
- A short list of themed findings, each with a real source URL you consulted
- Prefer sources from the last 12 months
- Flag anything single-source or uncertain
- Separate fact from inference
"""


def build_prompt(topic: str, deep: bool = False, web: bool = False) -> str:
    """Pick the brief by mode. `deep` = exhaustive web research; `web` = quick
    web-grounded pass; neither = from-memory quick pass. `deep` wins if both set.
    """
    if deep:
        brief = DEEP_BRIEF
    elif web:
        brief = WEB_BRIEF
    else:
        brief = QUICK_BRIEF
    return brief.format(topic=topic)
