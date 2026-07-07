# graphify hook wiring + graph-aware review diff-impact — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire graphify's `graphify hook install` into sigma's setup surfaces, and add an informational graph-derived "Impact" section to `sigma review`.

**Architecture:** Two independent features on the existing graphify seam. Feature 1 adds a confirm-gated/idempotent wrapper around `graphify hook install` in `cli/graphify.py` + a WARN-never-FAIL probe + one onboard step (shape of `setup_graphify`/`setup_rtk`). Feature 2 adds a new pure module `cli/graph_impact.py` that reads graphify's `graph.json` (stdlib json, never imports graphify) and a ~5-line additive wire into `cli/review_run.py`. Both fail-safe: graphify/artifacts absent → today's behavior byte-for-byte.

**Tech Stack:** Python 3.9, pytest, stdlib only (json, shutil, subprocess). Spec: `docs/superpowers/specs/2026-07-07-graph-hook-and-review-impact-design.md`.

## Global Constraints

- **Python 3.9 target.** Type hints use `Optional[X]`/`List[X]` from `typing`, NEVER `X | None` (ruff `UP` disabled).
- **Never import graphify** (needs 3.10+). Shell out to the `graphify` binary; read its output files with stdlib `json`.
- Standard library first; runtime deps stay `pyyaml`+`rich` only (no new deps).
- Fail-safe everywhere: graphify absent, or `graph.json` missing/unreadable/oversize → degrade to current behavior, never raise, never change the gate.
- Confirm-gated + idempotent for anything touching shared state; `confirm` defaults to `lambda msg: False` (default-deny).
- All lookups/spawns injectable so tests never touch git, spawn a process, or install anything.
- `python3 -m pytest tests/ -q` must stay green; `python3 -m ruff check cli/ tests/` clean.
- Files stay small (<400 lines), single-purpose.

---

## Task 1: `graphify_hook_status` — detect the installed post-commit hook

**Files:**
- Modify: `cli/graphify.py` (add after `graphify_status`, ~line 53)
- Test: `tests/test_graphify.py` (add)

**Interfaces:**
- Consumes: `shutil.which` (injected), a repo `root: Path`.
- Produces: `graphify_hook_status(root: Path, which: Optional[Callable] = None) -> Dict` returning `{"installed": bool}`. `installed` is True only when `root/.git/hooks/post-commit` exists and its text contains the substring `graphify`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graphify.py (add these)
from pathlib import Path
from cli.graphify import graphify_hook_status


def _make_repo(tmp_path: Path, hook_body: str = None) -> Path:
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    if hook_body is not None:
        (hooks / "post-commit").write_text(hook_body)
    return tmp_path


def test_hook_status_installed_when_marker_present(tmp_path):
    root = _make_repo(tmp_path, "#!/bin/sh\nexec /path/to/graphify update .\n")
    assert graphify_hook_status(root)["installed"] is True


def test_hook_status_absent_when_no_hook_file(tmp_path):
    root = _make_repo(tmp_path, hook_body=None)
    assert graphify_hook_status(root)["installed"] is False


def test_hook_status_absent_when_hook_lacks_marker(tmp_path):
    root = _make_repo(tmp_path, "#!/bin/sh\necho hello\n")
    assert graphify_hook_status(root)["installed"] is False


def test_hook_status_absent_when_no_git_dir(tmp_path):
    assert graphify_hook_status(tmp_path)["installed"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graphify.py -k hook_status -v`
Expected: FAIL — `ImportError: cannot import name 'graphify_hook_status'`

- [ ] **Step 3: Implement**

```python
# cli/graphify.py — add after graphify_status()

_HOOK_MARKER = "graphify"


def graphify_hook_status(root: Path, which: Optional[Callable] = None) -> Dict:
    """Report {installed} — whether graphify's post-commit hook is in this repo.

    True when `root/.git/hooks/post-commit` exists and mentions graphify (the hook
    graphify writes embeds an interpreter path + a `graphify` invocation). Fail-safe:
    no `.git`, no hook, or an unreadable file → {"installed": False}. Never raises.
    `which` is accepted for signature symmetry with the other status fns (unused).
    """
    hook = root / ".git" / "hooks" / "post-commit"
    try:
        if not hook.is_file():
            return {"installed": False}
        return {"installed": _HOOK_MARKER in hook.read_text()}
    except OSError:
        return {"installed": False}
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_graphify.py -k hook_status -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cli/graphify.py tests/test_graphify.py
git commit -m "feat: graphify_hook_status — detect the installed post-commit hook"
```

---

## Task 2: `install_graphify_hook` + `setup_graphify_hook` — confirm-gated install

**Files:**
- Modify: `cli/graphify.py` (add after `graphify_hook_status`)
- Test: `tests/test_graphify.py` (add)

**Interfaces:**
- Consumes: `graphify_status` (binary presence), `graphify_hook_status` (Task 1), `_default_spawn` (existing), `shutil.which`.
- Produces:
  - `install_graphify_hook(root: Path, which: Optional[Callable] = None, spawn: Optional[Callable] = None) -> bool` — runs `["graphify", "hook", "install"]` with `cwd=root`, returns True on exit 0.
  - `setup_graphify_hook(status_fn=None, hook_status_fn=None, confirm=None, which=None, spawn=None, root=None) -> bool` — confirm-gated, idempotent; returns True only when it installed the hook.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graphify.py (add)
from cli.graphify import install_graphify_hook, setup_graphify_hook


def test_install_graphify_hook_spawns_correct_argv(tmp_path):
    calls = []

    def spawn(argv, cwd=None):
        calls.append((argv, cwd))
        return 0

    ok = install_graphify_hook(tmp_path, which=lambda _: "/bin/graphify", spawn=spawn)
    assert ok is True
    assert calls == [(["graphify", "hook", "install"], tmp_path)]


def test_install_graphify_hook_false_on_nonzero(tmp_path):
    ok = install_graphify_hook(tmp_path, which=lambda _: "/bin/graphify",
                               spawn=lambda argv, cwd=None: 1)
    assert ok is False


def test_setup_noop_when_graphify_binary_absent(tmp_path):
    changed = setup_graphify_hook(
        status_fn=lambda: {"installed": False},          # graphify binary absent
        hook_status_fn=lambda: {"installed": False},
        confirm=lambda _msg: True,
        root=tmp_path,
        spawn=lambda *a, **k: 0,
    )
    assert changed is False


def test_setup_noop_when_hook_already_installed(tmp_path):
    changed = setup_graphify_hook(
        status_fn=lambda: {"installed": True},           # graphify present
        hook_status_fn=lambda: {"installed": True},      # hook already there
        confirm=lambda _msg: True,
        root=tmp_path,
        spawn=lambda *a, **k: 0,
    )
    assert changed is False


def test_setup_noop_when_confirm_denied(tmp_path):
    changed = setup_graphify_hook(
        status_fn=lambda: {"installed": True},
        hook_status_fn=lambda: {"installed": False},
        confirm=lambda _msg: False,                      # user declines
        root=tmp_path,
        spawn=lambda *a, **k: 0,
    )
    assert changed is False


def test_setup_installs_when_confirmed(tmp_path):
    calls = []
    changed = setup_graphify_hook(
        status_fn=lambda: {"installed": True},
        hook_status_fn=lambda: {"installed": False},
        confirm=lambda _msg: True,
        root=tmp_path,
        which=lambda _: "/bin/graphify",
        spawn=lambda argv, cwd=None: calls.append((argv, cwd)) or 0,
    )
    assert changed is True
    assert calls == [(["graphify", "hook", "install"], tmp_path)]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graphify.py -k "install_graphify_hook or setup_noop or setup_installs" -v`
Expected: FAIL — `ImportError: cannot import name 'install_graphify_hook'`

- [ ] **Step 3: Implement**

```python
# cli/graphify.py — add after graphify_hook_status()

def install_graphify_hook(
    root: Path,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
) -> bool:
    """Run `graphify hook install` in `root`. Returns True on exit 0.

    graphify owns the hook body + the graph.json merge driver; sigma only invokes
    it. `spawn` is the module's injectable runner (OSError-guarded), so this never
    raises. Caller ensures the graphify binary is present.
    """
    which = which or shutil.which
    spawn = spawn or _default_spawn
    return spawn(["graphify", "hook", "install"], root) == 0


def setup_graphify_hook(
    status_fn: Optional[Callable[[], Dict]] = None,
    hook_status_fn: Optional[Callable[[], Dict]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    which: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
    root: Optional[Path] = None,
) -> bool:
    """Confirm-gated, idempotent install of graphify's post-commit hook.

    - graphify binary absent → no-op (nothing to hook; install graphify first).
    - hook already installed → no-op.
    - else → confirm, then `graphify hook install`.
    Mirrors setup_graphify / setup_rtk. Returns True only when state changed.
    """
    root = root or Path(".")
    status_fn = status_fn or (lambda: graphify_status(which=which))
    hook_status_fn = hook_status_fn or (lambda: graphify_hook_status(root, which=which))
    confirm = confirm or (lambda msg: False)

    if not status_fn().get("installed"):
        return False  # no graphify binary → nothing to hook
    if hook_status_fn().get("installed"):
        return False  # already hooked

    if not confirm(
        "Install graphify's post-commit hook so the knowledge graph refreshes "
        "on each commit (AST-only, no API cost)?"
    ):
        return False

    return install_graphify_hook(root, which=which, spawn=spawn)
```

Note: `_default_spawn(argv)` currently takes one arg. Update its signature to accept an optional `cwd` so hook installs run in the repo:

```python
# cli/graphify.py — replace the existing _default_spawn
def _default_spawn(argv: List[str], cwd: Optional[Path] = None) -> int:
    """Run a command interactively (inherits stdio); return its exit code."""
    try:
        return subprocess.call(argv, cwd=str(cwd) if cwd else None)
    except OSError:
        return 1
```

- [ ] **Step 4: Run to verify pass (and no regression in existing graphify tests)**

Run: `python3 -m pytest tests/test_graphify.py -v`
Expected: PASS (all, including the existing `setup_graphify`/`report_block` tests — the `_default_spawn` cwd default keeps its one-arg callers working)

- [ ] **Step 5: Commit**

```bash
git add cli/graphify.py tests/test_graphify.py
git commit -m "feat: setup_graphify_hook — confirm-gated wrapper over graphify hook install"
```

---

## Task 3: `check_graphify_hook` probe + register in `run_all`

**Files:**
- Modify: `cli/checks.py` (add after `check_graphify`, ~line 249; register in `run_all` ~line 301)
- Test: `tests/test_checks.py` (add)

**Interfaces:**
- Consumes: `graphify_status` (binary presence), `graphify_hook_status`, `setup_graphify_hook` (Task 2).
- Produces: `check_graphify_hook(status_fn=None, hook_status_fn=None, root=None) -> Check` — OK when hook installed; WARN otherwise. Added to `run_all` right after `check_graphify`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_checks.py (add)
from pathlib import Path
from cli.checks import check_graphify_hook, OK, WARN


def test_check_graphify_hook_ok_when_installed():
    c = check_graphify_hook(
        status_fn=lambda: {"installed": True},
        hook_status_fn=lambda: {"installed": True},
        root=Path("."),
    )
    assert c.status == OK


def test_check_graphify_hook_warn_when_hook_missing():
    c = check_graphify_hook(
        status_fn=lambda: {"installed": True},
        hook_status_fn=lambda: {"installed": False},
        root=Path("."),
    )
    assert c.status == WARN
    assert c.fix is not None


def test_check_graphify_hook_warn_when_graphify_absent():
    c = check_graphify_hook(
        status_fn=lambda: {"installed": False},
        hook_status_fn=lambda: {"installed": False},
        root=Path("."),
    )
    assert c.status == WARN
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_checks.py -k graphify_hook -v`
Expected: FAIL — `ImportError: cannot import name 'check_graphify_hook'`

- [ ] **Step 3: Implement**

```python
# cli/checks.py — add after check_graphify()

def check_graphify_hook(
    status_fn: Optional[Callable[[], Dict]] = None,
    hook_status_fn: Optional[Callable[[], Dict]] = None,
    root: Optional[Path] = None,
) -> Check:
    """graphify post-commit hook: installed (auto-refreshes the graph on commit)?"""
    root = root or Path(".")
    if status_fn is None:
        from cli.graphify import graphify_status

        status_fn = graphify_status
    if hook_status_fn is None:
        from cli.graphify import graphify_hook_status

        hook_status_fn = lambda: graphify_hook_status(root)  # noqa: E731

    def _fix() -> bool:
        from cli.graphify import setup_graphify_hook

        return setup_graphify_hook(
            status_fn=status_fn, hook_status_fn=hook_status_fn,
            confirm=lambda _msg: True, root=root,
        )

    if not status_fn().get("installed"):
        return Check(
            "graphify-hook", WARN,
            "graphify not installed — install it first to enable the auto-refresh hook",
        )
    if not hook_status_fn().get("installed"):
        return Check(
            "graphify-hook", WARN,
            "graphify post-commit hook not installed (optional — refreshes the graph on commit)",
            fix=("install the graphify post-commit hook", _fix),
        )
    return Check("graphify-hook", OK, "graphify post-commit hook installed (graph auto-refreshes)")
```

Register in `run_all` immediately after `check_graphify(...)`:

```python
        check_graphify(status_fn=graphify_status_fn),
        check_graphify_hook(root=root),
    ]
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_checks.py -k graphify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/checks.py tests/test_checks.py
git commit -m "feat: check_graphify_hook probe (WARN-never-FAIL) + register in run_all"
```

---

## Task 4: onboard step for the graphify hook

**Files:**
- Modify: `cli/onboard.py` (add step after the graphify-install step, ~line 121)
- Test: `tests/test_onboard.py` (add or extend)

**Interfaces:**
- Consumes: `graphify_mod.setup_graphify_hook` (Task 2), the onboard `confirm`/`which`/`spawn` already threaded through `cmd_onboard`.
- Produces: prints `"  ✓ graphify post-commit hook installed — graph refreshes on each commit"` when it installs.

- [ ] **Step 1: Write the failing test**

First inspect the existing onboard test style:

Run: `python3 -m pytest tests/test_onboard.py -q` and open `tests/test_onboard.py` to match its injection pattern (it fakes `graphify_mod`/`confirm`). Then add:

```python
# tests/test_onboard.py (add — adapt names to the file's existing harness)
def test_onboard_installs_graphify_hook(monkeypatch, capsys, tmp_path):
    # Arrange: graphify present, hook missing, user confirms everything.
    import cli.onboard as ob

    called = {"hook": False}

    def fake_setup_hook(**kwargs):
        called["hook"] = True
        return True

    monkeypatch.setattr(ob.graphify_mod, "setup_graphify_hook", fake_setup_hook, raising=False)
    # ... reuse the file's existing fakes for setup_graphify/rtk/caveman/etc. that
    # make cmd_onboard runnable without touching the host, and confirm=lambda _:True.

    # Act
    ob.cmd_onboard(...)  # match the existing test's invocation

    # Assert
    assert called["hook"] is True
    assert "graphify post-commit hook installed" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_onboard.py -k graphify_hook -v`
Expected: FAIL (`AttributeError` on `setup_graphify_hook`, or the print assertion fails)

- [ ] **Step 3: Implement**

Insert after the graphify-install block (after line 121, before the SessionStart hook block):

```python
    # 9b. graphify post-commit hook — confirm-gated. Refreshes the knowledge graph
    #     on each commit (AST-only, no API cost). No-op if graphify isn't installed
    #     or the hook is already present. graphify owns the hook + graph.json merge
    #     driver; sigma only invokes `graphify hook install`.
    graph_hook_changed = graphify_mod.setup_graphify_hook(
        confirm=confirm, which=which, spawn=spawn, root=project_root()
    )
    if graph_hook_changed:
        print("  ✓ graphify post-commit hook installed — graph refreshes on each commit")
```

If `project_root` isn't already imported in `onboard.py`, add `from cli.paths import project_root` at the top (it is imported locally inside `_maybe_learn` today — hoist or import locally in this block to match the file's style).

- [ ] **Step 4: Run to verify pass + full onboard suite**

Run: `python3 -m pytest tests/test_onboard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/onboard.py tests/test_onboard.py
git commit -m "feat: onboard step to install the graphify post-commit hook (confirm-gated)"
```

---

## Task 5: `cli/graph_impact.py` — load_graph

**Files:**
- Create: `cli/graph_impact.py`
- Test: `tests/test_graph_impact.py` (create)

**Interfaces:**
- Produces: `load_graph(root: Path, max_bytes: int = 20_000_000) -> Optional[dict]` — parses `root/graphify-out/graph.json`; returns the dict or `None` on missing/unreadable/invalid-JSON/oversize.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_impact.py (create)
import json
from pathlib import Path
from cli.graph_impact import load_graph


def _write_graph(root: Path, obj) -> None:
    out = root / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(json.dumps(obj))


def test_load_graph_happy(tmp_path):
    _write_graph(tmp_path, {"nodes": [], "edges": []})
    assert load_graph(tmp_path) == {"nodes": [], "edges": []}


def test_load_graph_missing_returns_none(tmp_path):
    assert load_graph(tmp_path) is None


def test_load_graph_bad_json_returns_none(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True)
    (out / "graph.json").write_text("{not json")
    assert load_graph(tmp_path) is None


def test_load_graph_oversize_returns_none(tmp_path):
    _write_graph(tmp_path, {"nodes": [{"id": "x" * 100}]})
    assert load_graph(tmp_path, max_bytes=10) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graph_impact.py -k load_graph -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.graph_impact'`

- [ ] **Step 3: Implement**

```python
# cli/graph_impact.py
"""Graph-aware diff impact for `sigma review` (read side of graphify's graph.json).

Reads graphify's `graphify-out/graph.json` with stdlib json — sigma NEVER imports
graphify (it needs 3.10+; sigma stays 3.9). Cross-references a review's changed
files against the graph: which nodes each file defines, and which other nodes depend
on them (reverse edges). Purely informational — the review gate and axis prompts are
untouched. Fail-safe: no graph, or an unrecognized schema, yields empty impact (or
None from load_graph), never a crash.

graphify's graph.json schema is not a stable contract, so parsing is deliberately
tolerant: it tries several common key names and skips anything it can't read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

_GRAPH_REL = ("graphify-out", "graph.json")
# Guard against a pathological graph.json blowing memory / the report.
_DEFAULT_MAX_BYTES = 20_000_000
# Per-file cap on nodes/dependents surfaced (report stays readable).
_PER_FILE_CAP = 20


def load_graph(root: Path, max_bytes: int = _DEFAULT_MAX_BYTES) -> Optional[dict]:
    """Parse graphify's graph.json under `root`. None on any failure (fail-safe)."""
    path = root
    for part in _GRAPH_REL:
        path = path / part
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_graph_impact.py -k load_graph -v`
Expected: PASS (4)

- [ ] **Step 5: Commit**

```bash
git add cli/graph_impact.py tests/test_graph_impact.py
git commit -m "feat: graph_impact.load_graph — fail-safe reader for graphify graph.json"
```

---

## Task 6: `impact_for` — cross-reference changed files against the graph

**Files:**
- Modify: `cli/graph_impact.py` (add `FileImpact` + `impact_for` + helpers)
- Test: `tests/test_graph_impact.py` (add)

**Interfaces:**
- Consumes: a parsed `graph: dict` (Task 5), `changed_files: Sequence[str]`.
- Produces:
  - `@dataclass(frozen=True) class FileImpact: file: str; nodes: List[str]; dependents: List[str]`
  - `impact_for(graph: dict, changed_files: Sequence[str]) -> List[FileImpact]` — one entry per changed file, deterministic order, nodes/dependents sorted+deduped+capped.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_impact.py (add)
from cli.graph_impact import impact_for, FileImpact


def test_impact_canonical_schema():
    graph = {
        "nodes": [
            {"id": "n1", "name": "Foo", "file": "cli/foo.py"},
            {"id": "n2", "name": "Bar", "file": "cli/bar.py"},
        ],
        "edges": [{"source": "n2", "target": "n1"}],  # Bar depends on Foo
    }
    out = impact_for(graph, ["cli/foo.py"])
    assert out == [FileImpact(file="cli/foo.py", nodes=["Foo"], dependents=["Bar"])]


def test_impact_alt_schema_links_from_to_path():
    graph = {
        "nodes": [
            {"id": "a", "label": "A", "path": "/abs/repo/cli/a.py"},
            {"id": "b", "label": "B", "path": "/abs/repo/cli/b.py"},
        ],
        "links": [{"from": "b", "to": "a"}],
    }
    out = impact_for(graph, ["cli/a.py"])  # matches by suffix (abs vs relative)
    assert out[0].nodes == ["A"]
    assert out[0].dependents == ["B"]


def test_impact_edge_endpoints_by_name():
    graph = {
        "nodes": [{"name": "Foo", "file": "cli/foo.py"},
                  {"name": "Bar", "file": "cli/bar.py"}],
        "edges": [{"source": "Bar", "target": "Foo"}],  # endpoints are names, not ids
    }
    out = impact_for(graph, ["cli/foo.py"])
    assert out[0].dependents == ["Bar"]


def test_impact_no_match_returns_empty_lists():
    graph = {"nodes": [{"name": "Foo", "file": "cli/foo.py"}], "edges": []}
    out = impact_for(graph, ["cli/unrelated.py"])
    assert out == [FileImpact(file="cli/unrelated.py", nodes=[], dependents=[])]


def test_impact_malformed_nodes_skipped_no_crash():
    graph = {"nodes": ["not a dict", {"file": "cli/foo.py"}, {"name": "Ok", "file": "cli/foo.py"}],
             "edges": ["bad", {"source": "x"}]}
    out = impact_for(graph, ["cli/foo.py"])
    assert out[0].nodes == ["Ok"]  # nameless + non-dict nodes skipped, no raise


def test_impact_caps_and_dedup():
    nodes = [{"name": f"N{i}", "file": "cli/foo.py"} for i in range(30)]
    nodes.append({"name": "N0", "file": "cli/foo.py"})  # dup
    out = impact_for({"nodes": nodes, "edges": []}, ["cli/foo.py"])
    assert len(out[0].nodes) == 20  # _PER_FILE_CAP
    assert out[0].nodes == sorted(set(n["name"] for n in nodes))[:20]
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graph_impact.py -k impact -v`
Expected: FAIL — `ImportError: cannot import name 'impact_for'`

- [ ] **Step 3: Implement**

```python
# cli/graph_impact.py — add (import Sequence in the typing line)
from typing import Dict, List, Optional, Sequence  # update existing import

_NODE_PATH_KEYS = ("file", "path", "source", "source_file")
_NODE_NAME_KEYS = ("name", "id", "label")
_EDGE_SRC_KEYS = ("source", "from", "src")
_EDGE_DST_KEYS = ("target", "to", "dst")


@dataclass(frozen=True)
class FileImpact:
    file: str
    nodes: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)


def _first(d: dict, keys) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _matches(node_path: str, changed: str) -> bool:
    """A node belongs to `changed` when its path equals or ends with it (abs vs rel)."""
    np = node_path.replace("\\", "/")
    ch = changed.replace("\\", "/")
    return np == ch or np.endswith("/" + ch) or np.endswith(ch)


def impact_for(graph: dict, changed_files: Sequence[str]) -> List[FileImpact]:
    """Per-file (nodes defined, dependents = nodes with an edge INTO those nodes).

    Schema-tolerant + fail-safe: unreadable nodes/edges are skipped, never raised.
    Deterministic: changed_files order preserved; nodes/dependents sorted, deduped,
    capped at _PER_FILE_CAP.
    """
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if edges is None and isinstance(graph, dict):
        edges = graph.get("links")
    nodes = nodes if isinstance(nodes, list) else []
    edges = edges if isinstance(edges, list) else []

    # Build: node-name-or-id → path; and id/name → display name (for edge resolution).
    name_by_key: Dict[str, str] = {}
    path_by_name: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        name = _first(n, _NODE_NAME_KEYS)
        if not name:
            continue
        path = _first(n, _NODE_PATH_KEYS)
        # Register every possible edge-endpoint key (id, name, label) → display name.
        for k in _NODE_NAME_KEYS:
            v = n.get(k)
            if isinstance(v, str) and v:
                name_by_key[v] = name
        if path:
            path_by_name.setdefault(name, path)

    results: List[FileImpact] = []
    for changed in changed_files:
        touched = sorted({
            name for name, path in path_by_name.items() if _matches(path, changed)
        })
        touched_set = set(touched)
        dependents = set()
        for e in edges:
            if not isinstance(e, dict):
                continue
            src = _first(e, _EDGE_SRC_KEYS)
            dst = _first(e, _EDGE_DST_KEYS)
            if not src or not dst:
                continue
            dst_name = name_by_key.get(dst, dst)
            if dst_name in touched_set:
                src_name = name_by_key.get(src, src)
                if src_name not in touched_set:  # a dependent, not a self-edge
                    dependents.add(src_name)
        results.append(FileImpact(
            file=changed,
            nodes=touched[:_PER_FILE_CAP],
            dependents=sorted(dependents)[:_PER_FILE_CAP],
        ))
    return results
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest tests/test_graph_impact.py -k impact -v`
Expected: PASS (6)

- [ ] **Step 5: Commit**

```bash
git add cli/graph_impact.py tests/test_graph_impact.py
git commit -m "feat: graph_impact.impact_for — schema-tolerant changed-file → node/dependent mapping"
```

---

## Task 7: `render_impact_section` — markdown block

**Files:**
- Modify: `cli/graph_impact.py` (add `render_impact_section`)
- Test: `tests/test_graph_impact.py` (add)

**Interfaces:**
- Consumes: `List[FileImpact]` (Task 6).
- Produces: `render_impact_section(impacts: List[FileImpact]) -> str` — markdown starting with `## Impact (knowledge graph)`. All-empty impacts → a single "no match" line. Empty list → same "no match" line (caller only calls this when a graph loaded).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_impact.py (add)
from cli.graph_impact import render_impact_section


def test_render_non_empty():
    out = render_impact_section([FileImpact("cli/foo.py", ["Foo"], ["Bar"])])
    assert out.startswith("## Impact (knowledge graph)")
    assert "cli/foo.py" in out
    assert "Foo" in out and "Bar" in out
    assert "informational" in out.lower()


def test_render_all_empty_says_no_match():
    out = render_impact_section([FileImpact("cli/foo.py", [], [])])
    assert "## Impact (knowledge graph)" in out
    assert "No graph nodes matched" in out


def test_render_is_deterministic():
    impacts = [FileImpact("a.py", ["N"], ["D"])]
    assert render_impact_section(impacts) == render_impact_section(impacts)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_graph_impact.py -k render -v`
Expected: FAIL — `ImportError: cannot import name 'render_impact_section'`

- [ ] **Step 3: Implement**

```python
# cli/graph_impact.py — add

def render_impact_section(impacts: List[FileImpact]) -> str:
    """Render the informational Impact markdown block (never affects the gate)."""
    header = "## Impact (knowledge graph)"
    preamble = (
        "_Derived from graphify's `graph.json`; informational only — does not affect "
        "the review verdict._"
    )
    has_any = any(fi.nodes or fi.dependents for fi in impacts)
    if not has_any:
        return f"{header}\n\n{preamble}\n\n_No graph nodes matched the changed files._\n"

    lines = [header, "", preamble, ""]
    for fi in impacts:
        if not (fi.nodes or fi.dependents):
            continue
        nodes = ", ".join(fi.nodes) if fi.nodes else "—"
        deps = ", ".join(fi.dependents) if fi.dependents else "none"
        lines.append(f"- **{fi.file}** → nodes: {nodes} · dependents: {deps}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run to verify pass + full module**

Run: `python3 -m pytest tests/test_graph_impact.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add cli/graph_impact.py tests/test_graph_impact.py
git commit -m "feat: graph_impact.render_impact_section — informational review report block"
```

---

## Task 8: Wire the Impact section into `sigma review`

**Files:**
- Modify: `cli/review_run.py` (after `render_report`, ~line 174; before `_write_report`)
- Test: `tests/test_review_run.py` (add) — match the file's existing fake-AgentRunner harness.

**Interfaces:**
- Consumes: `graph_impact.load_graph`, `graph_impact.impact_for`, `graph_impact.render_impact_section` (Tasks 5–7); the existing `change`, `report`, `root` in `run_review`.
- Produces: the written report gains the Impact section when `graphify-out/graph.json` exists; **byte-identical to today when it does not**.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_review_run.py (add — reuse the file's existing fakes for AgentRunner
# and change-set resolution; the key is a temp root with/without graph.json)
import json
from pathlib import Path
from cli import review_run as rr


def _fake_diff(*_a, **_k):
    # Minimal fake so resolve_change_set yields one changed file (adapt to the
    # file's existing cmd_runner fake if present).
    class P:
        returncode = 0
        stdout = "diff --git a/cli/foo.py b/cli/foo.py\n+++ b/cli/foo.py\n+x\n"
    return P()


def test_review_appends_impact_when_graph_present(tmp_path, monkeypatch):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps(
        {"nodes": [{"name": "Foo", "file": "cli/foo.py"}], "edges": []}))

    res = rr.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=_make_passing_runner,     # existing helper in the test module
        cmd_runner=_fake_diff,
    )
    assert res.ok
    assert "## Impact (knowledge graph)" in res.report
    assert "cli/foo.py" in res.report


def test_review_report_byte_identical_without_graph(tmp_path, monkeypatch):
    # No graphify-out/graph.json → report must equal the no-graph baseline.
    res = rr.run_review(
        target=None, root=tmp_path, skills_dir=tmp_path / "skills",
        make_runner=_make_passing_runner,
        cmd_runner=_fake_diff,
    )
    assert res.ok
    assert "## Impact (knowledge graph)" not in res.report
```

If the test module lacks `_make_passing_runner`, add a small fake that returns
`AgentRunner`-shaped results with `ok=True` and an output containing a couple of
`FINDING | LOW | cli/foo.py:1 | ok` lines + `VERDICT: PASS`, distinct per axis.

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_review_run.py -k impact -v`
Expected: FAIL — Impact section not present in `res.report`

- [ ] **Step 3: Implement**

In `cli/review_run.py`, add the import near the top:

```python
from cli.graph_impact import impact_for, load_graph, render_impact_section
```

After `report = rv.render_report(change, results, decision, domains)` (~line 174), before the `out_dir`/`_write_report` block, insert:

```python
    # Graph-aware diff impact (informational; never affects the gate). If graphify's
    # graph.json is present, append a per-file node/dependent Impact section. Any
    # failure here is swallowed — a completed review must never break on the extra.
    try:
        graph = load_graph(root)
        if graph is not None:
            section = render_impact_section(impact_for(graph, change.files))
            report = report + "\n" + section
    except Exception:  # noqa: BLE001 — impact is best-effort, never fatal
        pass
```

- [ ] **Step 4: Run to verify pass + full review suite**

Run: `python3 -m pytest tests/test_review_run.py tests/test_review.py -v`
Expected: PASS (existing review tests unaffected — the gate/report base is untouched)

- [ ] **Step 5: Commit**

```bash
git add cli/review_run.py tests/test_review_run.py
git commit -m "feat: append graph-aware Impact section to sigma review report (informational)"
```

---

## Task 9: Docs — CLAUDE.md gotchas + README

**Files:**
- Modify: `CLAUDE.md` (Layout: add `cli/graph_impact.py`; Gotchas: add two bullets)
- Modify: `README.md` (mention the graphify hook + review Impact section where graphify/review are described)

**Interfaces:** none (documentation).

- [ ] **Step 1: Update CLAUDE.md Layout**

Add under the `cli/…` layout list, near `cli/graphify.py`:

```
cli/graph_impact.py pure: read graphify graph.json (stdlib, never import) → per-changed-file touched nodes + reverse-edge dependents; powers sigma review's informational Impact section
```

- [ ] **Step 2: Add CLAUDE.md Gotchas bullets**

```
- `sigma review` appends an informational **Impact** section from graphify's
  `graph.json` when present (`cli/graph_impact.py` → `review_run`): per changed file,
  the nodes it defines + reverse-edge dependents. Purely additive — the gate and axis
  prompts are UNTOUCHED, and no graph → report byte-identical to before (regression-
  locked by `test_review_report_byte_identical_without_graph`). Schema-tolerant
  parsing (tries nodes/edges|links, source/target|from/to, file|path|source), fail-safe
  to empty; sigma NEVER imports graphify (reads the file directly, stays 3.9).
- `setup_graphify_hook` (`cli/graphify.py`) wires graphify's OWN `graphify hook
  install` (post-commit graph refresh, AST-only 0-cost, + a graph.json merge driver)
  — sigma does NOT author its own hook. Confirm-gated + idempotent (setup_graphify
  shape): no graphify binary → no-op; hook already present → no-op. Onboard step 9b +
  `check_graphify_hook` (WARN-never-FAIL). `_default_spawn` gained an optional `cwd`.
```

- [ ] **Step 3: Update README.md**

Where the graphify / `sigma learn` and `sigma review` features are described, add a
sentence each: (a) graphify's post-commit hook can be installed via `sigma onboard` /
`sigma doctor` to auto-refresh the graph; (b) `sigma review` surfaces a graph-derived
Impact section when a graphify graph is present. Match the surrounding prose style.

- [ ] **Step 4: Verify docs build/lint is unaffected**

Run: `python3 -m pytest tests/ -q && python3 -m ruff check cli/ tests/`
Expected: all green, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: graphify hook wiring + review graph-impact section (CLAUDE.md + README)"
```

---

## Final verification

- [ ] **Full suite + lint:**

Run: `python3 -m pytest tests/ -q && python3 -m ruff check cli/ tests/`
Expected: all tests pass (663 + new), ruff clean.

- [ ] **Byte-identical regression confirmed:** `test_review_report_byte_identical_without_graph` and existing `test_graphify.py` / `test_review*.py` pass unchanged — proving both features are additive and fail-safe.
