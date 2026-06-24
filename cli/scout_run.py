"""`sigma scout` — discover relevant skills on skillsmp.com and install on approval.

The thin, side-effectful half of scout. Pure scoring/ranking/dedup live in
`cli/scout.py`; this module does the network call (stdlib `urllib`, no `requests`
dependency), aggregates across domain queries, surfaces a ranked table, and — only
on explicit confirmation — `git clone`s a chosen skill into the target directory.

Fail-safe: the skillsmp API being down, rate-limited, or returning garbage yields
an empty result + a banner, never a crash. Nothing is ever auto-installed; a human
picks from the surfaced table (the "surface, never auto-resolve" law).

The fetcher, the cloner, and the confirm are all injectable so tests never touch
the network, git, or the filesystem outside tmp.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli import scout
from cli.scout import SkillHit

_SEARCH_URL = "https://skillsmp.com/api/v1/skills/search"
_API_KEY_NAME = "SKILLSMP_API_KEY"
_TIMEOUT = 15
_PER_QUERY_LIMIT = 25


@dataclass
class ScoutResult:
    ok: bool
    hits: List[SkillHit] = field(default_factory=list)
    installed: List[str] = field(default_factory=list)
    note: Optional[str] = None


def _default_fetch(url: str, api_key: Optional[str]) -> Optional[dict]:
    """GET a skillsmp URL, return parsed JSON or None on any failure (fail-safe)."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 (https only)
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw)
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _default_clone(github_url: str, dest: Path) -> bool:
    """git clone a skill repo into dest/<repo>. Returns True on success."""
    import subprocess

    try:
        dest.mkdir(parents=True, exist_ok=True)
        code = subprocess.call(["git", "clone", "--depth", "1", github_url], cwd=str(dest))
        return code == 0
    except OSError:
        return False


def search_url(query: str, category: str = "", recent: bool = False, limit: int = _PER_QUERY_LIMIT) -> str:
    """Build a skillsmp search URL (kept pure + testable)."""
    params = {"q": query, "limit": str(limit), "sortBy": "recent" if recent else "stars"}
    if category:
        params["category"] = category
    return f"{_SEARCH_URL}?{urllib.parse.urlencode(params)}"


def discover(
    domains: List[str],
    category: Optional[str] = None,
    recent: bool = False,
    skills_dir: Optional[Path] = None,
    fetch: Optional[Callable[[str, Optional[str]], Optional[dict]]] = None,
    api_key: Optional[str] = None,
) -> ScoutResult:
    """Query skillsmp per domain, aggregate, dedup vs the bundle, and rank.

    Fail-safe: if every query fails (API down/rate-limited), returns ok=False with a
    banner and no hits. Partial success (some queries return) still ranks what came
    back. Never raises.
    """
    fetch = fetch or _default_fetch
    if api_key is None:
        api_key = _read_api_key()

    queries = scout.domain_queries(domains)
    if not queries:
        return ScoutResult(ok=False, note="no known sigma domains selected")

    all_hits: List[SkillHit] = []
    any_response = False
    for _domain, query, default_cat in queries:
        url = search_url(query, category or default_cat, recent=recent)
        payload = fetch(url, api_key)
        if payload is None:
            continue
        any_response = True
        all_hits.extend(scout.parse_search_response(payload, domains))

    if not any_response:
        return ScoutResult(
            ok=False,
            note="skillsmp.com unreachable or rate-limited — try later "
            "(a free SKILLSMP_API_KEY in ~/.sigma/.env raises the daily limit)",
        )

    # Dedup across domains (same skill surfaced by two queries) and vs the bundle.
    seen = set()
    unique: List[SkillHit] = []
    for h in all_hits:
        if h.key in seen:
            continue
        seen.add(h.key)
        unique.append(h)
    fresh = scout.dedup_against_bundle(unique, skills_dir)
    ranked = scout.rank(fresh)
    note = None if ranked else "no new relevant skills found (all matches already in the bundle)"
    return ScoutResult(ok=True, hits=ranked, note=note)


def install_hits(
    hits: List[SkillHit],
    dest: Path,
    confirm: Callable[[SkillHit], bool],
    clone: Optional[Callable[[str, Path], bool]] = None,
) -> List[str]:
    """For each hit the user confirms, clone it into `dest`. Returns installed keys.

    Per-hit confirm so the human approves each skill individually (license + fit
    are surfaced in the prompt). Never auto-installs.
    """
    clone = clone or _default_clone
    installed: List[str] = []
    for h in hits:
        if confirm(h) and clone(h.github_url, dest):
            installed.append(h.key)
    return installed


def _read_api_key() -> Optional[str]:
    """Read SKILLSMP_API_KEY from the env or ~/.sigma/.env (never prompted).

    Optional — anonymous access works at a lower daily rate. Importing secrets here
    (not at module top) keeps this function self-contained and easy to stub.
    """
    import os

    from cli import secrets

    ambient = os.environ.get(_API_KEY_NAME)
    if ambient:
        return ambient
    return secrets.read_env().get(_API_KEY_NAME) or None
