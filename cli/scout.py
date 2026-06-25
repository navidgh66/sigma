"""Pure logic for `sigma scout` — keep sigma's skill bundle fresh from skillsmp.com.

skillsmp.com aggregates a very large community catalog of agent skills. `scout`
queries it per sigma domain, scores each hit for relevance, drops anything already
in the bundle, and ranks the survivors. The network call and the install live in
`cli/scout_run.py`; everything here is pure and deterministic so it tests without a
network or filesystem dependency.

A hit is NEVER auto-installed — `scout_run` surfaces the ranked table and a human
picks (the same "surface, never auto-resolve" law as contradiction flagging).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Map each sigma domain to a search query + a skillsmp category slug. The category
# slugs are skillsmp's own ("data-ai" is its broad umbrella for ML/AI skills); the
# query carries the domain-specific terms that drive relevance scoring.
_DOMAIN_QUERY: Dict[str, Tuple[str, str]] = {
    "classic-ml": ("machine learning scikit feature engineering", "data-ai"),
    "deep-learning": ("deep learning pytorch tensorflow neural network", "data-ai"),
    "nlp": ("nlp text transformers tokenization language", "data-ai"),
    "rl": ("reinforcement learning policy reward agent", "data-ai"),
    "data-analysis": ("data analysis pandas visualization eda", "data-ai"),
    "data-engineering": ("data engineering pipeline etl spark warehouse", "data-ai"),
    "ai-agent-engineering": ("ai agent tool calling orchestration mcp", "data-ai"),
    "mlops": ("mlops model deployment monitoring serving", "data-ai"),
    "llm-engineering": ("llm prompt rag fine-tuning evaluation", "data-ai"),
}

# Cross-cutting terms relevant to every sigma domain, scored as a small bonus.
_CROSS_CUTTING = ("evaluation", "testing", "reproducibility", "experiment", "dataset")

# Default cap on how many candidates scout surfaces, so a broad sweep stays scannable.
_DEFAULT_LIMIT = 20
# A hit must clear this relevance floor to surface at all. The star bump is capped at
# 1.0, so a floor just above it guarantees a hit needs at least ONE real domain-keyword
# overlap (worth 2.0) — popularity alone never surfaces pure noise.
_RELEVANCE_FLOOR = 1.5
# Cap on hits surfaced from any single author, so one prolific publisher can't flood
# the table and crowd out diverse, relevant alternatives.
_DEFAULT_MAX_PER_AUTHOR = 3


@dataclass(frozen=True)
class SkillHit:
    """One catalog entry from skillsmp, normalized."""

    name: str
    description: str
    github_url: str
    author: str = ""
    stars: int = 0
    score: float = 0.0

    @property
    def key(self) -> str:
        """Stable identity for dedup: normalized github url, else name."""
        return _norm_repo(self.github_url) or self.name.strip().lower()


def domain_queries(domains: List[str]) -> List[Tuple[str, str, str]]:
    """Return (domain, query, category) for each known domain. Unknown → skipped."""
    out: List[Tuple[str, str, str]] = []
    for d in domains:
        if d in _DOMAIN_QUERY:
            query, category = _DOMAIN_QUERY[d]
            out.append((d, query, category))
    return out


def score_relevance(hit: SkillHit, domains: List[str]) -> float:
    """Deterministic relevance score for a hit against the selected domains.

    Combines keyword overlap with each domain's query terms, a cross-cutting bonus,
    and gentle popularity/quality signals (log-ish star bump). Higher is better.
    """
    # Tokenize BOTH sides and intersect on whole tokens — a raw substring test would
    # credit "rag" for "sto-rag-e"/"f-rag-ment" and "data" for "meta-data", inflating
    # relevance on noise. Whole-token matching is the fix.
    text_tokens = set(_tokenize(f"{hit.name} {hit.description}"))
    terms = set()
    for d in domains:
        if d in _DOMAIN_QUERY:
            terms.update(_tokenize(_DOMAIN_QUERY[d][0]))
    overlap = len(terms & text_tokens)
    cross = sum(1 for t in _CROSS_CUTTING if t in text_tokens)
    # Star bump is capped so a popular-but-irrelevant skill never outranks a
    # relevant one purely on popularity.
    star_bump = min(hit.stars, 1000) / 1000.0
    return float(overlap) * 2.0 + float(cross) * 0.5 + star_bump


def rank(
    hits: List[SkillHit],
    limit: int = _DEFAULT_LIMIT,
    max_per_author: int = _DEFAULT_MAX_PER_AUTHOR,
) -> List[SkillHit]:
    """Drop sub-floor noise, sort, cap per author, then cap at `limit`.

    1. Relevance FLOOR: a hit below `_RELEVANCE_FLOOR` (i.e. no real domain-keyword
       overlap, surviving only on the capped star bump) is dropped — scout never
       surfaces pure noise just to fill the table.
    2. Sort by score (desc), then stars (desc), then name. Deterministic — ties never
       break on input order.
    3. Per-author cap: at most `max_per_author` hits from one author, so a prolific
       publisher can't crowd out diverse alternatives.
    4. Cap at `limit`.
    """
    floored = [h for h in hits if h.score >= _RELEVANCE_FLOOR]
    ordered = sorted(floored, key=lambda h: (-h.score, -h.stars, h.name.lower()))
    out: List[SkillHit] = []
    per_author: Dict[str, int] = {}
    for h in ordered:
        author = (h.author or "").strip().lower()
        if author:
            if per_author.get(author, 0) >= max_per_author:
                continue
            per_author[author] = per_author.get(author, 0) + 1
        out.append(h)
        if len(out) >= limit:
            break
    return out


def dedup_against_bundle(hits: List[SkillHit], skills_dir: Optional[Path]) -> List[SkillHit]:
    """Drop hits whose repo/name already exists under the bundle.

    Matches a hit's normalized repo against every directory name under `skills_dir`
    (recursively) and against the `origin`/source recorded in any SKILL.md. Missing
    dir → nothing to dedup against (returns the input).
    """
    if not skills_dir or not skills_dir.exists():
        return list(hits)
    present = _bundle_keys(skills_dir)
    return [h for h in hits if h.key not in present and _slug(h.name) not in present]


def _bundle_keys(skills_dir: Path) -> set:
    keys = set()
    for child in skills_dir.rglob("*"):
        if child.is_dir():
            keys.add(child.name.strip().lower())
    # Also index any github source recorded in a SKILL.md frontmatter.
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            text = skill_md.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip().lower()
            if s.startswith("source:") or s.startswith("origin:") or s.startswith("repository:"):
                val = s.split(":", 1)[1].strip()
                norm = _norm_repo(val)
                if norm:
                    keys.add(norm)
    return keys


def parse_search_response(payload: dict, domains: List[str]) -> List[SkillHit]:
    """Turn one skillsmp /search JSON payload into scored SkillHits.

    Tolerant of missing fields (a partial record degrades, never raises). Returns
    [] for a non-dict or a payload without a skills array.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return []
    hits: List[SkillHit] = []
    for raw in skills:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        github_url = str(raw.get("githubUrl") or "").strip()
        if not name or not github_url:
            continue  # nothing to install without a name + repo
        hit = SkillHit(
            name=name,
            description=str(raw.get("description") or "").strip(),
            github_url=github_url,
            author=str(raw.get("author") or "").strip(),
            stars=_as_int(raw.get("stars")),
        )
        hits.append(SkillHit(**{**hit.__dict__, "score": score_relevance(hit, domains)}))
    return hits


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def _norm_repo(url: str) -> str:
    """Normalize a github url/handle to 'owner/repo' (lowercase), or ''."""
    if not url:
        return ""
    u = url.strip().lower().rstrip("/")
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^(www\.)?github\.com/", "", u)
    u = re.sub(r"\.git$", "", u)
    parts = [p for p in u.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
