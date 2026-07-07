import json
import urllib.error

from cli.search_providers import available_tools, run_search_tool


def test_available_tools_filters_missing_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("cli.secrets.read_env", lambda: {})
    assert available_tools(["firecrawl"]) == []


def test_available_tools_keeps_present_key(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    assert available_tools(["firecrawl"]) == ["firecrawl"]


def test_available_tools_ignores_unknown_tool(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    assert available_tools(["not-a-real-tool"]) == []


def test_run_search_tool_success(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fake_fetch(url, api_key, timeout=None):
        assert api_key == "fake-key"
        return {"data": [{"title": "Example", "url": "https://example.com", "markdown": "Found X."}]}

    result = run_search_tool("firecrawl", "graph neural nets", fetch=fake_fetch)
    assert result.ok is True
    assert result.model == "firecrawl"
    assert "example.com" in result.text
    assert "Found X" in result.text


def test_run_search_tool_missing_key_is_skipped(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.setattr("cli.secrets.read_env", lambda: {})
    result = run_search_tool("firecrawl", "topic", fetch=lambda url, key, timeout=None: {"data": []})
    assert result.ok is False
    assert result.skipped is True
    assert "API key" in result.error


def test_run_search_tool_fetch_failure_maps_to_result(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def failing_fetch(url, api_key, timeout=None):
        return None  # fetch failed (network/timeout/bad response)

    result = run_search_tool("firecrawl", "topic", fetch=failing_fetch)
    assert result.ok is False
    assert result.skipped is False
    assert result.error is not None


def test_run_search_tool_unknown_tool():
    result = run_search_tool("not-a-real-tool", "topic")
    assert result.ok is False
    assert result.skipped is True


def test_run_search_tool_forwards_timeout_to_fetch(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    seen = {}

    def fetch(url, api_key, timeout=None):
        seen["timeout"] = timeout
        return {"data": []}

    run_search_tool("firecrawl", "topic", fetch=fetch, timeout=5)
    assert seen["timeout"] == 5


def test_run_search_tool_handles_non_dict_top_level_json(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")

    def fetch(url, api_key, timeout=None):
        return ["unexpected", "list", "shape"]  # not a dict

    result = run_search_tool("firecrawl", "topic", fetch=fetch)
    assert result.ok is True
    assert result.text == ""


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
