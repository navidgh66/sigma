"""Pure logic for `sigma prune` — find loaded-but-unused MCP servers + plugins.

Every enabled plugin and connected MCP server injects its tool schemas / skill
descriptions into EVERY Claude context — a large, recurring token tax. `prune`
inventories what's loaded, estimates each item's context weight, cross-references
recent actual usage from session transcripts, and ranks "heavy + unused" disable
candidates.

This module is pure: it parses already-loaded dicts/records and returns rankings.
The file reads, transcript scan, and the (reversible) settings write live in
`cli/prune_run.py`. Disable is never an uninstall — an item used recently is never a
candidate, and missing usage data is treated conservatively as "used" so we never
prune on absent evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# Item kinds.
KIND_PLUGIN = "plugin"
KIND_MCP_USER = "mcp-user"      # user-level server in ~/.claude.json (manual to disable)
KIND_MCP_PROJECT = "mcp-project"  # project .mcp.json server (disable via settings list)

# Static per-kind context-weight estimates (tokens), used as a FALLBACK when the
# real tool count is unknown. MCP servers carry full tool schemas (often many tools)
# → heaviest; plugins bring skills/commands/maybe an MCP. Deliberately rough, like
# cost.py's static factors — they rank, they don't bill.
_KIND_WEIGHT = {
    KIND_MCP_USER: 8000,
    KIND_MCP_PROJECT: 8000,
    KIND_PLUGIN: 3000,
}
_DEFAULT_WEIGHT = 3000
# Rough per-tool schema cost (tokens) when an item's distinct tool count is known.
# An MCP tool's JSON schema (name + description + params) is ~250-400 tokens; 300 is
# a sane midpoint. Weight = tool_count * this, so a 100-tool server dwarfs a 2-tool one.
_PER_TOOL_WEIGHT = 300


@dataclass(frozen=True)
class InventoryItem:
    """One loaded context contributor.

    `tool_count` is the distinct tool-schema count observed for this item across
    history (0/unknown → fall back to the per-kind estimate). It lets weight scale
    with a server's real schema width instead of a flat per-kind constant.
    """

    name: str
    kind: str
    tool_count: int = 0

    @property
    def weight(self) -> int:
        if self.tool_count > 0:
            return self.tool_count * _PER_TOOL_WEIGHT
        return _KIND_WEIGHT.get(self.kind, _DEFAULT_WEIGHT)


@dataclass(frozen=True)
class Candidate:
    """A ranked prune suggestion: a loaded item with its usage + weight.

    `low_confidence` marks an item surfaced because it was RARELY used (within an
    `idle_threshold`), not truly unused — a judgment call for the human, never an
    auto-disable. A zero-use item is high-confidence (low_confidence=False).
    """

    item: InventoryItem
    uses: int
    reversible: bool  # True if sigma can disable it via a settings flag
    low_confidence: bool = False

    @property
    def name(self) -> str:
        return self.item.name

    @property
    def kind(self) -> str:
        return self.item.kind

    @property
    def weight(self) -> int:
        return self.item.weight


def parse_plugins(settings: Optional[dict]) -> List[InventoryItem]:
    """Enabled plugins from settings.json `enabledPlugins` (only the True ones)."""
    if not isinstance(settings, dict):
        return []
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return []
    return [
        InventoryItem(name=str(name), kind=KIND_PLUGIN)
        for name, on in enabled.items()
        if on is True
    ]


def parse_mcp_servers(
    claude_json: Optional[dict],
    project_mcp: Optional[dict] = None,
) -> List[InventoryItem]:
    """MCP servers from ~/.claude.json (user) and a project .mcp.json (project)."""
    items: List[InventoryItem] = []
    if isinstance(claude_json, dict):
        servers = claude_json.get("mcpServers")
        if isinstance(servers, dict):
            items += [InventoryItem(name=str(n), kind=KIND_MCP_USER) for n in servers]
    if isinstance(project_mcp, dict):
        servers = project_mcp.get("mcpServers")
        if isinstance(servers, dict):
            items += [InventoryItem(name=str(n), kind=KIND_MCP_PROJECT) for n in servers]
    return items


def belongs(tool_name: str, item: InventoryItem) -> bool:
    """True if an observed tool/skill invocation belongs to an inventory item.

    - MCP tools surface as `mcp__<server>__<tool>` (a plugin-provided server appears
      as `mcp__plugin_<plugin>_<server>__...`). We match the item's name as a token.
    - Plugin skills/commands surface via the `Skill` tool as `<plugin>:<skill>`.
    Matching is token-based + substring-guarded so `github` doesn't match `github2`.
    """
    if not tool_name:
        return False
    base = _short_name(item.name)  # strip @marketplace
    low = tool_name.lower()
    base_low = base.lower()

    if low.startswith("mcp__"):
        # The server segment sits between the mcp__ prefix and the trailing __<tool>.
        # A plugin-provided server reads `plugin_<plugin>_<server>`. The plugin name
        # may contain hyphens AND the harness may render them as `_`, so normalize
        # both separators to a single `_` and look for the base as a contiguous run.
        middle = low[len("mcp__"):]
        server = middle.split("__", 1)[0]
        norm_server = f"_{server.replace('-', '_')}_"
        norm_base = f"_{base_low.replace('-', '_')}_"
        return norm_base in norm_server
    # Skill / command form: "<plugin>:<name>" or bare plugin name.
    head = low.split(":", 1)[0]
    return head == base_low


def usage_counts(
    invocations: List[str],
    skill_refs: List[str],
    items: List[InventoryItem],
) -> Dict[str, int]:
    """Count how many observed invocations belong to each inventory item.

    `invocations` are tool_use names (incl. `mcp__...`); `skill_refs` are the
    `<plugin>:<skill>` strings pulled from `Skill` tool inputs. Returns name→count.
    """
    counts: Dict[str, int] = {it.name: 0 for it in items}
    all_signals = list(invocations) + list(skill_refs)
    for it in items:
        counts[it.name] = sum(1 for sig in all_signals if belongs(sig, it))
    return counts


def rank_candidates(
    items: List[InventoryItem],
    usage: Dict[str, int],
    reversible_kinds: Optional[set] = None,
    idle_threshold: int = 0,
) -> List[Candidate]:
    """Rank disable candidates: idle items, heaviest first.

    An item with more than `idle_threshold` uses is excluded (kept). With the
    default `idle_threshold=0`, only TRULY unused items surface (unchanged behavior).
    Raise it (e.g. 1) to also surface RARELY-used items — those are flagged
    `low_confidence` (a judgment call for the human, never auto-disabled). Among
    the survivors, sort by weight desc, then name. `reversible_kinds` marks which
    kinds sigma can disable via a settings flag (the rest are surfaced for manual edit).
    """
    reversible_kinds = reversible_kinds if reversible_kinds is not None else {
        KIND_PLUGIN, KIND_MCP_PROJECT,
    }
    cands = [
        Candidate(
            item=it,
            uses=usage.get(it.name, 0),
            reversible=it.kind in reversible_kinds,
            low_confidence=usage.get(it.name, 0) > 0,  # surfaced despite some use
        )
        for it in items
        if usage.get(it.name, 0) <= idle_threshold
    ]
    return sorted(cands, key=lambda c: (-c.weight, c.name.lower()))


def total_weight(candidates: List[Candidate]) -> int:
    """Sum of estimated context tokens the candidates would free if disabled."""
    return sum(c.weight for c in candidates)


def _short_name(name: str) -> str:
    """`code-review@claude-plugins-official` → `code-review`; passthrough otherwise."""
    return name.split("@", 1)[0].strip()
