"""HTTP search-tool adapters: grounded web search alongside the model-CLI
adapters in cli/models.py. First: Firecrawl. Same ModelResult output shape as
cli/models.py so cli/research.py's aggregate()/synthesize() treat both tiers
uniformly.

Fail-safe throughout: missing key, HTTP failure, or malformed response all
degrade to a ModelResult, never raise. Mirrors cli/scout_run.py's fetch
pattern (stdlib urllib, injectable fetch for tests — no real network calls
in the test suite).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from cli import secrets
from cli.models import ModelResult

_FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
_TIMEOUT = 30


@dataclass
class SearchAdapter:
    """Describes one HTTP search-tool provider."""

    name: str
    api_key_env: str


ADAPTERS: Dict[str, SearchAdapter] = {
    "firecrawl": SearchAdapter(name="firecrawl", api_key_env="FIRECRAWL_API_KEY"),
}


def _api_key(env_name: str) -> Optional[str]:
    """Ambient env var wins, else ~/.sigma/.env — same precedence as secrets.py."""
    ambient = os.environ.get(env_name)
    if ambient:
        return ambient
    return secrets.read_env().get(env_name)


def available_tools(requested: List[str]) -> List[str]:
    """Return requested tools whose API key is configured, preserving order."""
    out: List[str] = []
    for name in requested:
        adapter = ADAPTERS.get(name)
        if adapter and _api_key(adapter.api_key_env):
            out.append(name)
    return out


def _default_fetch(url: str, api_key: str, timeout: int = _TIMEOUT) -> Optional[dict]:
    """POST a Firecrawl search request; return parsed JSON or None on failure."""
    body = json.dumps({"query": url}).encode("utf-8")
    req = urllib.request.Request(
        _FIRECRAWL_SEARCH_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw)
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _format_findings(data: dict) -> str:
    """Render Firecrawl's search response into themed-findings text."""
    items = data.get("data") or []
    if not isinstance(items, list) or not items:
        return ""
    lines: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        snippet = item.get("markdown") or item.get("description") or ""
        lines.append(f"- {title} ({url})\n  {snippet.strip()}")
    return "\n".join(lines)


def run_search_tool(
    tool: str,
    prompt: str,
    fetch: Callable[..., Optional[dict]] = _default_fetch,
    timeout: int = _TIMEOUT,
) -> ModelResult:
    """Run one search tool's HTTP call for `prompt`. Never raises."""
    adapter = ADAPTERS.get(tool)
    if adapter is None:
        return ModelResult(model=tool, ok=False, text="", error="unknown tool", skipped=True)

    api_key = _api_key(adapter.api_key_env)
    if not api_key:
        return ModelResult(
            model=tool, ok=False, text="", error="API key not configured", skipped=True
        )

    data = fetch(prompt, api_key, timeout=timeout)
    if data is None:
        return ModelResult(model=tool, ok=False, text="", error="search request failed")

    text = _format_findings(data)
    return ModelResult(model=tool, ok=True, text=text)
