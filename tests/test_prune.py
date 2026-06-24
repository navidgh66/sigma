"""Tests for cli.prune — pure inventory/usage/ranking logic (no files, no clock)."""

from __future__ import annotations

from cli.prune import (
    KIND_MCP_PROJECT,
    KIND_MCP_USER,
    KIND_PLUGIN,
    InventoryItem,
    belongs,
    parse_mcp_servers,
    parse_plugins,
    rank_candidates,
    total_weight,
    usage_counts,
)


# --------------------------- parse loaded --------------------------- #
def test_parse_plugins_only_enabled():
    settings = {"enabledPlugins": {"a@m": True, "b@m": False, "c@m": True}}
    names = {p.name for p in parse_plugins(settings)}
    assert names == {"a@m", "c@m"}
    assert all(p.kind == KIND_PLUGIN for p in parse_plugins(settings))


def test_parse_plugins_bad_shape_safe():
    assert parse_plugins(None) == []
    assert parse_plugins({"enabledPlugins": "nope"}) == []


def test_parse_mcp_user_and_project():
    claude_json = {"mcpServers": {"databricks": {}, "atlassian": {}}}
    project = {"mcpServers": {"localdb": {}}}
    items = parse_mcp_servers(claude_json, project)
    kinds = {i.name: i.kind for i in items}
    assert kinds["databricks"] == KIND_MCP_USER
    assert kinds["localdb"] == KIND_MCP_PROJECT


# --------------------------- belongs matching --------------------------- #
def test_belongs_matches_mcp_server_token():
    gh = InventoryItem("github@market", KIND_PLUGIN)
    assert belongs("mcp__plugin_github_github__create_pull_request", gh)


def test_belongs_matches_skill_namespace():
    sigma = InventoryItem("sigma@sigma", KIND_PLUGIN)
    assert belongs("sigma:sigma-grilling", sigma)


def test_belongs_no_false_substring_match():
    db = InventoryItem("databricks", KIND_MCP_USER)
    # a different server whose name merely contains the token must not match
    assert not belongs("mcp__databricksx__run", db)
    assert belongs("mcp__databricks__run", db)


# --------------------------- usage counting --------------------------- #
def test_usage_counts_per_item():
    items = [
        InventoryItem("github@m", KIND_PLUGIN),
        InventoryItem("slack@m", KIND_PLUGIN),
    ]
    invocations = [
        "mcp__plugin_github_github__create_pull_request",
        "mcp__plugin_github_github__list_pull_requests",
        "Bash",
    ]
    counts = usage_counts(invocations, skill_refs=[], items=items)
    assert counts["github@m"] == 2
    assert counts["slack@m"] == 0


# --------------------------- ranking --------------------------- #
def test_rank_excludes_used_and_orders_by_weight():
    items = [
        InventoryItem("used-mcp", KIND_MCP_USER),
        InventoryItem("idle-mcp", KIND_MCP_USER),     # heavy + unused
        InventoryItem("idle-plugin", KIND_PLUGIN),    # lighter + unused
    ]
    usage = {"used-mcp": 3, "idle-mcp": 0, "idle-plugin": 0}
    cands = rank_candidates(items, usage)
    names = [c.name for c in cands]
    assert "used-mcp" not in names          # used → kept
    assert names == ["idle-mcp", "idle-plugin"]  # heavier MCP first


def test_rank_marks_reversibility():
    items = [
        InventoryItem("proj-mcp", KIND_MCP_PROJECT),
        InventoryItem("user-mcp", KIND_MCP_USER),
        InventoryItem("plug", KIND_PLUGIN),
    ]
    usage = {i.name: 0 for i in items}
    by_name = {c.name: c for c in rank_candidates(items, usage)}
    assert by_name["proj-mcp"].reversible is True   # project mcp → settings flag
    assert by_name["plug"].reversible is True        # plugin → settings flag
    assert by_name["user-mcp"].reversible is False   # user mcp → manual edit


def test_total_weight_sums_candidates():
    items = [InventoryItem("a", KIND_PLUGIN), InventoryItem("b", KIND_MCP_USER)]
    usage = {"a": 0, "b": 0}
    cands = rank_candidates(items, usage)
    assert total_weight(cands) == sum(c.weight for c in cands)
    assert total_weight(cands) > 0
