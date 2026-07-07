# Design: native deep-web-crawl for the Firecrawl search-tool tier

## Context

sigma's research module (`cli/search_providers.py`) has one HTTP search-tool
adapter, Firecrawl, wired to its `/v1/search` endpoint only — snippet-only
findings (title + short markdown/description per result). An external
`deep-research` skill (from the ECC plugin, not sigma) additionally *scrapes*
top result URLs for full-page content before synthesizing. sigma doesn't ship
or depend on that skill (deliberately — see `commands/research.md`'s
conditional "if available" language), but the capability itself — deeper
per-source content, not just snippets — is worth having natively in sigma's
own pipeline, since sigma already pays for the Firecrawl dependency.

Goal: extend the existing Firecrawl adapter to scrape full-page content for
the top few search results when `--deep` is requested, and fold that richer
text into the same `ModelResult` findings that already flow into
`aggregate()`/`synthesize()`. No new dependency, no new provider, no new
external skill reliance.

## Scope decisions (confirmed)

- **Trigger**: scraping only fires on `--deep` (exhaustive mode). `--web`
  (quick web-grounded) and plain quick research stay snippet-only — no latency
  or credit-cost regression for the common case.
- **Breadth**: scrape the top **3** result URLs per search-tool call. Matches
  the deep-research skill's own "3-5 key sources in full" guidance; bounded
  cost/latency.
- **Provider**: Firecrawl only (the only configured search-tool adapter
  today). No exa, no new MCP dependency — keeps sigma's "no paid API beyond
  what's already opted into" design intact.

## Design

### 1. New HTTP call: `_default_scrape`

`cli/search_providers.py` gains a second stdlib-urllib POST, mirroring
`_default_fetch`'s shape exactly (same try/except → `None` on any failure):

```python
_FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"

def _default_scrape(url: str, api_key: str, timeout: int = _TIMEOUT) -> Optional[dict]:
    """POST a Firecrawl scrape request for one URL; return parsed JSON or None."""
    body = json.dumps({"url": url, "formats": ["markdown"]}).encode("utf-8")
    req = urllib.request.Request(
        _FIRECRAWL_SCRAPE_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw)
    except (urllib.error.URLError, ValueError, OSError):
        return None
```

Response shape (Firecrawl `/v1/scrape`): `{"success": true, "data": {"markdown": "...", "metadata": {...}}}`.
`_extract_scraped_text(data: dict) -> str` pulls `data["data"]["markdown"]`
defensively (same `isinstance` guards as `_format_findings`), returns `""` on
any shape mismatch.

### 2. `run_search_tool` gains a `deep` param

```python
def run_search_tool(
    tool: str,
    prompt: str,
    fetch: Callable[..., Optional[dict]] = _default_fetch,
    scrape: Callable[..., Optional[dict]] = _default_scrape,
    timeout: int = _TIMEOUT,
    deep: bool = False,
    scrape_top_n: int = 3,
) -> ModelResult:
```

Behavior: after the existing search call succeeds, if `deep` is `True`, take
the top `scrape_top_n` items' URLs from the parsed search response and call
`scrape` on each (sequentially — bounded to 3, no new thread pool needed
inside a single already-pooled future). Each scrape failure is caught and
that item silently falls back to its snippet — never aborts the whole tool
call. Both `fetch` and `scrape` stay injectable for tests, matching the
existing pattern.

### 3. Findings rendering

`_format_findings` is extended (or a sibling `_format_deep_findings` is
added — implementation detail for the plan) to render, per item: the
existing snippet line, followed by a `**Full content:**` block with the
scraped markdown when available for that item. Items without a successful
scrape keep exactly today's snippet-only rendering — no behavior change when
`deep=False` (regression-locked, mirrors the byte-identical guarantees
elsewhere in this codebase).

### 4. Wiring from `cli/research.py`

`run_research`'s `tool_futures` currently ignores `deep`/`web` entirely:

```python
tool_futures = {t: pool.submit(search_runner, t, topic) for t in requested_tools}
```

Changes to:

```python
tool_futures = {t: pool.submit(search_runner, t, topic, deep=deep) for t in requested_tools}
```

`web=True` (quick web-grounded) does **not** set `deep=True` for the tool
tier — only `--deep` does, matching the confirmed trigger scope. This is a
one-line, additive change; the existing `deep` param already exists on
`run_research`'s signature and is already true/false-resolved by the CLI's
`--deep` flag today (it currently only affects the model-CLI tier's
`web_search` toggle).

### 5. Fail-safe guarantees (unchanged discipline)

- No Firecrawl key configured → tool skipped entirely (`available_tools`
  gate, unchanged).
- Search call itself fails → `ModelResult(ok=False, ...)`, unchanged.
- Search succeeds but one or more scrapes fail → those items degrade to
  snippet-only; the tool call still returns `ok=True` with whatever content
  it has. Never raises.
- `deep=False` → zero scrape calls issued, zero new HTTP requests, output
  byte-identical to pre-change behavior (test-locked).

## Testing

- `tests/test_search_providers.py` gains: scrape-success case (findings
  include full-content block), scrape-failure case (falls back to snippet,
  no crash), `deep=False` byte-identical case, `scrape_top_n` boundary
  (exactly N of the results get scraped, rest stay snippet-only).
- `tests/test_research.py`: `run_research`'s `tool_futures` call is asserted
  to pass `deep=True` only when the research-level `deep` flag is set, and
  `deep=False` when only `web=True`.

## Non-goals

- No exa or other new search-tool provider — Firecrawl only, per existing
  design.
- No crawl() (multi-page site crawl) — scrape() of individual result URLs
  only, per the confirmed "search + scrape top N" scope (crawl was explicitly
  rejected as heavier/costlier).
- No change to the model-CLI tier (claude/gemini/gpt) — this is scoped to the
  Firecrawl search-tool adapter only.
