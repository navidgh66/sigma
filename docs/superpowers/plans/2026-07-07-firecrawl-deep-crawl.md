# Plan: native Firecrawl deep-crawl for sigma's research module

Design: `docs/superpowers/specs/2026-07-07-firecrawl-deep-crawl-design.md`

TDD throughout: write the failing test, then the minimal implementation, per task.

## Task 1 — `_default_scrape` + `_extract_scraped_text` in `cli/search_providers.py`

**Test file:** `tests/test_search_providers.py`

Add:

```python
def test_default_scrape_returns_parsed_json_on_success(monkeypatch):
    calls = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"success": True, "data": {"markdown": "Full page text."}}).encode()

    def fake_urlopen(req, timeout=None):
        calls["url"] = req.full_url
        calls["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("cli.search_providers.urllib.request.urlopen", fake_urlopen)
    from cli.search_providers import _default_scrape

    result = _default_scrape("https://example.com/page", "fake-key", timeout=7)
    assert result == {"success": True, "data": {"markdown": "Full page text."}}
    assert calls["url"] == "https://api.firecrawl.dev/v1/scrape"
    assert calls["timeout"] == 7


def test_default_scrape_returns_none_on_error(monkeypatch):
    def raising_urlopen(req, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr("cli.search_providers.urllib.request.urlopen", raising_urlopen)
    from cli.search_providers import _default_scrape

    assert _default_scrape("https://example.com", "fake-key") is None


def test_extract_scraped_text_reads_markdown():
    from cli.search_providers import _extract_scraped_text

    assert _extract_scraped_text({"data": {"markdown": "Body text."}}) == "Body text."


def test_extract_scraped_text_handles_malformed_shapes():
    from cli.search_providers import _extract_scraped_text

    assert _extract_scraped_text({}) == ""
    assert _extract_scraped_text({"data": "not-a-dict"}) == ""
    assert _extract_scraped_text(["not", "a", "dict"]) == ""
```

Add `import urllib.error` to the test file's imports if not already present
(it already imports nothing from urllib today — add `import json`,
`import urllib.error` at top as needed for the fakes above).

**Implementation** (`cli/search_providers.py`):

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
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only)
            raw = resp.read().decode("utf-8", "replace")
        return json.loads(raw)
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _extract_scraped_text(data: dict) -> str:
    """Pull markdown body out of a Firecrawl scrape response, defensively."""
    if not isinstance(data, dict):
        return ""
    inner = data.get("data")
    if not isinstance(inner, dict):
        return ""
    text = inner.get("markdown")
    return text.strip() if isinstance(text, str) else ""
```

Run: `python3 -m pytest tests/test_search_providers.py -q` → new tests pass,
existing ones untouched.

## Task 2 — `run_search_tool` gains `deep`/`scrape`/`scrape_top_n`

**Test file:** `tests/test_search_providers.py`

Add:

```python
def test_run_search_tool_deep_scrapes_top_results(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fetch(url, api_key, timeout=None):
        return {
            "data": [
                {"title": "A", "url": "https://a.com", "markdown": "snippet A"},
                {"title": "B", "url": "https://b.com", "markdown": "snippet B"},
                {"title": "C", "url": "https://c.com", "markdown": "snippet C"},
                {"title": "D", "url": "https://d.com", "markdown": "snippet D"},
            ]
        }

    scraped_urls = []

    def scrape(url, api_key, timeout=None):
        scraped_urls.append(url)
        return {"data": {"markdown": f"FULL CONTENT for {url}"}}

    result = run_search_tool("firecrawl", "topic", fetch=fetch, scrape=scrape, deep=True)
    assert result.ok is True
    # Only the top 3 are scraped, not D.
    assert scraped_urls == ["https://a.com", "https://b.com", "https://c.com"]
    assert "FULL CONTENT for https://a.com" in result.text
    assert "FULL CONTENT for https://d.com" not in result.text
    assert "snippet D" in result.text  # D still present, snippet-only


def test_run_search_tool_deep_false_never_calls_scrape(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fetch(url, api_key, timeout=None):
        return {"data": [{"title": "A", "url": "https://a.com", "markdown": "snippet A"}]}

    def scrape(url, api_key, timeout=None):
        raise AssertionError("scrape must not be called when deep=False")

    result = run_search_tool("firecrawl", "topic", fetch=fetch, scrape=scrape, deep=False)
    assert result.ok is True
    assert "snippet A" in result.text


def test_run_search_tool_deep_scrape_failure_falls_back_to_snippet(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fetch(url, api_key, timeout=None):
        return {"data": [{"title": "A", "url": "https://a.com", "markdown": "snippet A"}]}

    def failing_scrape(url, api_key, timeout=None):
        return None

    result = run_search_tool("firecrawl", "topic", fetch=fetch, scrape=failing_scrape, deep=True)
    assert result.ok is True
    assert "snippet A" in result.text


def test_run_search_tool_deep_respects_custom_scrape_top_n(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fetch(url, api_key, timeout=None):
        return {
            "data": [
                {"title": "A", "url": "https://a.com", "markdown": "snippet A"},
                {"title": "B", "url": "https://b.com", "markdown": "snippet B"},
            ]
        }

    scraped_urls = []

    def scrape(url, api_key, timeout=None):
        scraped_urls.append(url)
        return {"data": {"markdown": "full"}}

    run_search_tool("firecrawl", "topic", fetch=fetch, scrape=scrape, deep=True, scrape_top_n=1)
    assert scraped_urls == ["https://a.com"]
```

**Implementation** (`cli/search_providers.py`):

Rewrite `_format_findings` to optionally accept scraped text per item, or
introduce a small helper that scrapes-then-renders. Keep it in one function
for cohesion — this module is small (120 lines today):

```python
def _format_findings(
    data: dict,
    scraped: Optional[Dict[str, str]] = None,
) -> str:
    """Render Firecrawl's search response into themed-findings text.

    `scraped` maps result URL -> full scraped markdown for items that were
    deep-crawled; items without an entry render snippet-only, unchanged from
    today's behavior.
    """
    if not isinstance(data, dict):
        return ""
    items = data.get("data") or []
    if not isinstance(items, list) or not items:
        return ""
    scraped = scraped or {}
    lines: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "(untitled)"
        url = item.get("url") or ""
        snippet = item.get("markdown") or item.get("description") or ""
        lines.append(f"- {title} ({url})\n  {snippet.strip()}")
        full_text = scraped.get(url)
        if full_text:
            lines.append(f"  **Full content:**\n  {full_text}")
    return "\n".join(lines)


def run_search_tool(
    tool: str,
    prompt: str,
    fetch: Callable[..., Optional[dict]] = _default_fetch,
    scrape: Callable[..., Optional[dict]] = _default_scrape,
    timeout: int = _TIMEOUT,
    deep: bool = False,
    scrape_top_n: int = 3,
) -> ModelResult:
    """Run one search tool's HTTP call for `prompt`. Never raises.

    When `deep` is True, additionally scrapes the top `scrape_top_n` result
    URLs for full-page content, folding it into the findings text. A scrape
    failure for any single URL degrades that item to snippet-only — never
    aborts the whole call. `deep=False` (default) issues zero scrape calls,
    byte-identical to pre-deep-crawl behavior.
    """
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

    scraped: Dict[str, str] = {}
    if deep and isinstance(data, dict):
        items = data.get("data") or []
        if isinstance(items, list):
            top_urls = [
                item.get("url")
                for item in items[:scrape_top_n]
                if isinstance(item, dict) and item.get("url")
            ]
            for url in top_urls:
                scraped_data = scrape(url, api_key, timeout=timeout)
                if scraped_data is None:
                    continue
                text = _extract_scraped_text(scraped_data)
                if text:
                    scraped[url] = text

    text = _format_findings(data, scraped=scraped)
    return ModelResult(model=tool, ok=True, text=text)
```

Run: `python3 -m pytest tests/test_search_providers.py -q` → all pass
(existing `_format_findings`-only tests must still pass since `scraped`
defaults to `None`/empty).

## Task 3 — wire `deep` from `cli/research.py`'s `run_research`

**Test file:** `tests/test_research.py`

The two existing search-tool fan-out tests define local `search_runner`
fakes with a 2-arg signature (`def search_runner(tool, prompt):`). Once
`run_research` passes `deep=` as a keyword, these break with `TypeError`.
Update both fakes to accept it (mirrors the existing `_call_runner`
tolerance note in CLAUDE.md's Gotchas for the model tier):

```python
def test_run_research_includes_search_tools():
    from cli.research import run_research

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, f"{model}-findings")

    def search_runner(tool, prompt, deep=False):
        return ModelResult(tool, True, f"{tool}-findings")

    results = run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner, search_runner=search_runner
    )
    models = {r.model for r in results}
    assert models == {"claude", "firecrawl"}


def test_run_research_passes_bare_topic_to_search_tools_not_full_brief():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["query"] = query
        return ModelResult(tool, True, "tool-findings")

    run_research("my topic", ["claude"], tools=["firecrawl"], runner=model_runner, search_runner=search_runner)
    assert seen["query"] == "my topic"
```

Add two new tests right after them:

```python
def test_run_research_deep_true_passes_deep_to_search_tools():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["deep"] = deep
        return ModelResult(tool, True, "tool-findings")

    run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner,
        search_runner=search_runner, deep=True,
    )
    assert seen["deep"] is True


def test_run_research_web_only_does_not_set_deep_on_search_tools():
    seen = {}

    def model_runner(model, prompt, deep=False):
        return ModelResult(model, True, "model-findings")

    def search_runner(tool, query, deep=False):
        seen["deep"] = deep
        return ModelResult(tool, True, "tool-findings")

    run_research(
        "topic", ["claude"], tools=["firecrawl"], runner=model_runner,
        search_runner=search_runner, web=True,
    )
    assert seen["deep"] is False
```

**Implementation** (`cli/research.py`, in `run_research`):

```python
        tool_futures = {
            t: pool.submit(search_runner, t, topic, deep=deep) for t in requested_tools
        }
```

(one-line change from `pool.submit(search_runner, t, topic)`). Note `web=True`
alone must NOT set `deep=True` on the tool tier — only the `deep` param
itself does, so no other change is needed; `web` only affects `web_search`
for the model tier already.

Run: `python3 -m pytest tests/test_research.py tests/test_search_providers.py -q`

## Task 4 — full verification

- `python3 -m pytest tests/ -q` — full suite green.
- `python3 -m ruff check cli/ tests/` — clean.
- Manual smoke (optional, only if `FIRECRAWL_API_KEY` is configured in this
  environment): `sigma research "test topic" --deep` and confirm no
  traceback; inspect `research.md` for a "Full content:" block under the
  firecrawl findings section if the key is live, or confirm graceful
  skip/failure text if not.

## Notes for the implementer

- Keep `_format_findings`'s new `scraped` param optional with a safe default
  so every existing call site and test that doesn't pass it keeps working
  unchanged.
- `scrape_top_n` slicing (`items[:scrape_top_n]`) must not error when there
  are fewer than N items — Python slicing handles this natively, just don't
  add a manual bounds check that could get it wrong.
- Do not thread `deep` into the *model*-CLI tier's fan-out — that already has
  its own `web_search = deep or web` toggle and is out of scope here.
