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
