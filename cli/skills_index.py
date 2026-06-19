"""Index ratcheted skills to detect contradictions between lessons.

When the loop ratchets a new lesson into skills/, a previous lesson for the same
domain + topic may already exist and disagree. This module finds those candidates
by a cheap, deterministic key match (same domain + same normalized topic) — no
model call. The caller flags them for human review; it never auto-resolves or
deletes (consistent with the ratchet's "failures are permanent, humans decide").
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

# Ratchet prefixes that describe the failure mode, not the topic itself.
# "session lesson:" is the manual /sigma-learn-lesson prefix — stripping it means a
# manually-captured lesson and a loop-born lesson on the same topic share a key
# (so they collide for contradiction detection + recall).
_NOISE_PREFIXES = (
    "verify failed:",
    "implement failed:",
    "logic failed:",
    "session lesson:",
)


def topic_key(title: str) -> str:
    """Normalize a lesson/task title to a stable topic slug.

    Strips ratchet noise prefixes ("verify failed:" etc.) so the same underlying
    task produces the same key regardless of which stage failed.
    """
    text = title.strip().lower()
    for prefix in _NOISE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or "lesson"


def parse_skill_meta(skill_md: Path) -> Dict[str, Optional[str]]:
    """Extract {domain, topic} from a ratcheted SKILL.md.

    domain comes from the `metadata:\\n  domain:` frontmatter; topic from the
    `# <title>` heading (run through topic_key).
    """
    domain: Optional[str] = None
    topic: Optional[str] = None
    try:
        text = skill_md.read_text()
    except OSError:
        return {"domain": None, "topic": None}

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("domain:"):
            domain = s.split(":", 1)[1].strip() or None
        elif topic is None and s.startswith("# "):
            topic = topic_key(s[2:])
    return {"domain": domain, "topic": topic}


def find_contradictions(skills_dir: Path, domain: Optional[str], topic: str) -> List[Path]:
    """Return existing SKILL.md paths that share the same domain + topic.

    A candidate contradiction: an earlier ratcheted lesson about the same work in
    the same domain. Empty list when none (or when domain is unknown).
    """
    if not domain or not skills_dir.exists():
        return []
    matches: List[Path] = []
    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        meta = parse_skill_meta(skill_md)
        if meta["domain"] == domain and meta["topic"] == topic:
            matches.append(skill_md)
    return matches
