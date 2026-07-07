# Usage Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sigma usage` command that thinly wraps `npx ccusage@latest` for Claude Code token/cache/cost visibility, distinct from sigma's own `sigma cost` op-ledger command, degrading gracefully when Node/npx is absent.

**Architecture:** `cli/usage.py` is a pure-ish module (node-runtime detection + argv builder), matching `cli/statusline.py`'s exact shape (injectable `which`/`spawn`, no real subprocess in tests). `cmd_usage` in `cli/main.py` wires it to a new `usage` subcommand using `argparse.REMAINDER` so all args after `usage` pass straight through to ccusage unmodified. `check_usage_tool` in `cli/checks.py` surfaces the same npx-absent gap as a WARN, mirroring `check_graphify` exactly.

**Tech Stack:** Python 3.9, stdlib only (`shutil.which`, `subprocess.call`), pytest, ruff.

## Global Constraints

- Python 3.9 target: `Optional[X]`/`List[X]` from `typing`, never `X | None`.
- No new runtime pip dependency — ccusage runs via `npx`, an external Node tool sigma shells out to, exactly like `cli/statusline.py` already does for ccstatusline. Sigma itself gains zero new dependencies.
- `which`/`spawn` must be injectable parameters (matching `cli/statusline.py`'s `_default_settings_path`/`_default_spawn` pattern) so tests never touch the network, spawn a real process, or require Node installed on the test machine.
- Fail-safe: missing npx/bunx → print a clear message, return exit code 0, never raise. This is WARN-never-FAIL, same as `check_graphify`.
- Zero new sigma-side flags: every argument after `usage` passes through to ccusage unmodified. `cli/usage.py` adds no flag parsing of its own beyond the prepend.
- Ruff must stay clean (`python3 -m ruff check cli/ tests/`); full suite must stay green (`python3 -m pytest tests/ -q`).

---

## File Structure

```
cli/usage.py         NEW — node_runtime_available() + build_argv()
cli/main.py          MODIFY — cmd_usage + `usage` subparser (REMAINDER passthrough)
cli/checks.py        MODIFY — check_usage_tool probe, wired into run_checks()
tests/test_usage.py  NEW
```

---

### Task 1: `cli/usage.py` — node-runtime detection + argv builder

**Files:**
- Create: `cli/usage.py`
- Test: `tests/test_usage.py`

**Interfaces:**
- Produces: `node_runtime_available(which: Optional[Callable] = None) -> bool`, `build_argv(passthrough_args: List[str]) -> List[str]`, `MISSING_NODE_MESSAGE: str` (module constant with the exact user-facing text).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_usage.py`:

```python
from cli.usage import MISSING_NODE_MESSAGE, build_argv, node_runtime_available


def test_node_runtime_available_true_when_npx_on_path():
    def fake_which(exe):
        return "/usr/bin/npx" if exe == "npx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_true_when_only_bunx_on_path():
    def fake_which(exe):
        return "/usr/bin/bunx" if exe == "bunx" else None

    assert node_runtime_available(which=fake_which) is True


def test_node_runtime_available_false_when_neither_present():
    assert node_runtime_available(which=lambda exe: None) is False


def test_build_argv_prepends_npx_ccusage():
    argv = build_argv([])
    assert argv == ["npx", "-y", "ccusage@latest"]


def test_build_argv_appends_passthrough_args_unmodified():
    argv = build_argv(["claude", "session", "--json"])
    assert argv == ["npx", "-y", "ccusage@latest", "claude", "session", "--json"]


def test_missing_node_message_mentions_npx_and_ccusage():
    assert "npx" in MISSING_NODE_MESSAGE.lower()
    assert "ccusage" in MISSING_NODE_MESSAGE.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_usage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.usage'`

- [ ] **Step 3: Write the implementation**

Create `cli/usage.py`:

```python
"""Thin wrapper around ccusage for Claude Code token/cache/cost visibility.

Distinct from cli/cost.py, which tracks sigma's OWN heavy-op token estimates
(review/loop/research) in sigma/costs.jsonl — this module reports Anthropic's
real session usage data, sourced from ccusage (https://ccusage.com), a mature
local-only CLI that already parses Claude Code's JSONL transcript tree.

Mirrors cli/statusline.py exactly: node-runtime detection and argv building are
pure/injectable so tests never touch the network or spawn a real process. No
new sigma-side flags — every arg after `usage` passes through to ccusage
unmodified.
"""

from __future__ import annotations

import shutil
from typing import Callable, List, Optional

MISSING_NODE_MESSAGE = (
    "npx not found — install Node.js to use 'sigma usage' (wraps ccusage: "
    "https://ccusage.com)"
)


def node_runtime_available(which: Optional[Callable] = None) -> bool:
    """True if `npx` or `bunx` is on PATH (needed to run ccusage)."""
    which = which or shutil.which
    return which("npx") is not None or which("bunx") is not None


def build_argv(passthrough_args: List[str]) -> List[str]:
    """Prepend the ccusage invocation to whatever args the user passed after
    `sigma usage`. Pure — no I/O, no mutation of the input list.
    """
    return ["npx", "-y", "ccusage@latest", *passthrough_args]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_usage.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Ruff check**

Run: `python3 -m ruff check cli/usage.py tests/test_usage.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add cli/usage.py tests/test_usage.py
git commit -m "feat: add cli/usage.py — node-runtime detection + ccusage argv builder"
```

---

### Task 2: `cmd_usage` + `usage` subcommand in `cli/main.py`

**Files:**
- Modify: `cli/main.py`
- Test: `tests/test_usage.py` (extend)

**Interfaces:**
- Consumes: `cli.usage.node_runtime_available`, `cli.usage.build_argv`, `cli.usage.MISSING_NODE_MESSAGE` (Task 1).
- Produces: `cmd_usage(args: argparse.Namespace) -> int`, a `usage` subparser with `nargs=argparse.REMAINDER` on a `usage_args` attribute.

- [ ] **Step 1: Read the current subcommand registration block to find the right insertion point**

Run: `grep -n "cmd_cost\|pi = sub.add_parser\|pr = sub.add_parser" cli/main.py`

Find where `cmd_cost` and its subparser are defined (near line 749 per the existing code) — the new `usage` command goes immediately after it, same style.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_usage.py`:

```python
import argparse

from cli.main import cmd_usage


def test_cmd_usage_calls_spawn_with_built_argv(monkeypatch):
    calls = []

    def fake_which(exe):
        return "/usr/bin/npx" if exe == "npx" else None

    def fake_spawn(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr("cli.usage.shutil.which", fake_which)
    monkeypatch.setattr("cli.main._usage_spawn", fake_spawn)

    args = argparse.Namespace(usage_args=["claude", "session"])
    rc = cmd_usage(args)

    assert rc == 0
    assert calls == [["npx", "-y", "ccusage@latest", "claude", "session"]]


def test_cmd_usage_returns_0_and_skips_spawn_when_node_missing(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: calls.append(argv))

    args = argparse.Namespace(usage_args=[])
    rc = cmd_usage(args)

    assert rc == 0
    assert calls == []  # spawn never called
    captured = capsys.readouterr()
    assert "npx" in captured.out.lower()


def test_cmd_usage_passes_through_exit_code(monkeypatch):
    monkeypatch.setattr("cli.usage.shutil.which", lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    monkeypatch.setattr("cli.main._usage_spawn", lambda argv: 7)

    args = argparse.Namespace(usage_args=[])
    rc = cmd_usage(args)

    assert rc == 7
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_usage.py -k cmd_usage -v`
Expected: FAIL with `ImportError: cannot import name 'cmd_usage'`

- [ ] **Step 4: Implement `cmd_usage` and `_usage_spawn`**

In `cli/main.py`, immediately after the `cmd_cost` function (after its closing `return 0`), add:

```python
# --------------------------------------------------------------------------- #
# usage (thin ccusage wrapper — real Claude Code session token/cache/cost)
# --------------------------------------------------------------------------- #
def _usage_spawn(argv: list) -> int:
    """Run ccusage interactively (inherits stdio); return its exit code."""
    import subprocess

    try:
        return subprocess.call(argv)
    except OSError:
        return 1


def cmd_usage(args: argparse.Namespace) -> int:
    from cli.usage import MISSING_NODE_MESSAGE, build_argv, node_runtime_available

    if not node_runtime_available():
        _print(MISSING_NODE_MESSAGE)
        return 0
    passthrough = list(getattr(args, "usage_args", None) or [])
    return _usage_spawn(build_argv(passthrough))
```

- [ ] **Step 5: Register the `usage` subparser**

Find the `cmd_cost` subparser registration (search for `sub.add_parser("cost"`) and add immediately after it:

```python
pu = sub.add_parser(
    "usage",
    help="Claude Code token/cache/cost usage (wraps ccusage)",
)
pu.add_argument("usage_args", nargs=argparse.REMAINDER, help="passthrough args for ccusage")
pu.set_defaults(func=cmd_usage)
```

Confirm `argparse` is already imported at the top of `cli/main.py` (it is — used throughout for `argparse.Namespace`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_usage.py -v`
Expected: PASS (9 tests total: 6 from Task 1 + 3 new)

- [ ] **Step 7: Manual smoke test of the CLI wiring**

Run: `python3 -m cli.main usage --help 2>&1 | head -5`
Expected: no traceback (argparse's REMAINDER may swallow `--help` into passthrough rather than showing sigma's own help — that's correct behavior, since `--help` should reach ccusage, not sigma, once REMAINDER captures it. Confirm no Python exception either way.)

Run: `python3 -m cli.main usage 2>&1 | head -10`
Expected: either ccusage's real output (if Node is installed) or the `MISSING_NODE_MESSAGE` fail-safe line — no traceback either way.

- [ ] **Step 8: Run full test suite + ruff**

Run: `python3 -m pytest tests/ -q`
Expected: all pass, no regressions.

Run: `python3 -m ruff check cli/main.py tests/test_usage.py`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add cli/main.py tests/test_usage.py
git commit -m "feat: add sigma usage command (thin ccusage wrapper)"
```

---

### Task 3: `check_usage_tool` probe in `cli/checks.py`

**Files:**
- Modify: `cli/checks.py`
- Test: `tests/test_checks.py` (extend if it exists, else create)

**Interfaces:**
- Consumes: `cli.usage.node_runtime_available` (Task 1).
- Produces: `check_usage_tool(which: Optional[Callable] = None) -> Check`, wired into `run_checks()`'s returned list.

- [ ] **Step 1: Check for an existing test file and confirm `run_checks`'s signature**

Run: `test -f tests/test_checks.py && echo EXISTS || echo MISSING`
Run: `grep -n "^def run_checks" cli/checks.py`

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_checks.py` (create if missing, with these plus necessary imports: `from cli.checks import check_usage_tool, OK, WARN`):

```python
def test_check_usage_tool_ok_when_node_runtime_present():
    check = check_usage_tool(which=lambda exe: "/usr/bin/npx" if exe == "npx" else None)
    assert check.status == OK
    assert check.name == "usage"


def test_check_usage_tool_warn_when_node_runtime_absent():
    check = check_usage_tool(which=lambda exe: None)
    assert check.status == WARN
    assert "npx" in check.detail.lower() or "node" in check.detail.lower()
    assert check.fix is None
```

Note: `check_usage_tool` has no `fix` — unlike `check_graphify` (which can `_fix()` by installing graphify), there's nothing sigma can auto-install here (Node/npm installation is out of scope, matches the spec's non-goal "no auto-install of Node/npx"). `fix=None` is correct and intentional, not an oversight.

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_checks.py -k usage_tool -v`
Expected: FAIL with `ImportError: cannot import name 'check_usage_tool'`

- [ ] **Step 4: Implement `check_usage_tool`**

In `cli/checks.py`, immediately after `check_graphify` (before the blank-line-separated `_pip_install` helper, or before whatever function currently follows `check_graphify` — insert right after `check_graphify`'s closing `return Check(...)` line), add:

```python
def check_usage_tool(which: Optional[Callable] = None) -> Check:
    """Node runtime (npx/bunx) for `sigma usage` (wraps ccusage): available?"""
    from cli.usage import node_runtime_available

    if not node_runtime_available(which=which):
        return Check(
            "usage", WARN,
            "npx/bunx not found (optional — 'sigma usage' wraps ccusage for "
            "Claude Code token/cost visibility)",
        )
    return Check("usage", OK, "npx/bunx available (sigma usage can run ccusage)")
```

- [ ] **Step 5: Wire it into `run_checks()`**

Find the `run_checks()` function's returned list (containing `check_graphify(status_fn=graphify_status_fn)` per the existing code) and add `check_usage_tool(),` as a new entry, e.g.:

```python
        check_graphify(status_fn=graphify_status_fn),
        check_graphify_hook(root=root),
        check_usage_tool(),
    ]
```

(Match the exact surrounding syntax/indentation of the list literal you find — read the actual current `run_checks()` body first, since line numbers may have shifted.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_checks.py -v`
Expected: PASS, no regressions in existing check tests.

- [ ] **Step 7: Run `sigma doctor` manually to confirm the new check surfaces**

Run: `python3 -m cli.main doctor --check 2>&1 | grep -i usage`
Expected: a line mentioning "usage" with either OK or WARN status, no traceback. Note: `--check` exits 1 on any FAIL — WARN does not fail the gate (confirm this by checking the exit code too: `python3 -m cli.main doctor --check; echo "exit: $?"` — a WARN-only usage check must not by itself flip this to a nonzero exit, unless other unrelated checks in this environment are already FAILing).

- [ ] **Step 8: Ruff check + full suite**

Run: `python3 -m ruff check cli/checks.py tests/test_checks.py`
Expected: no errors.

Run: `python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add cli/checks.py tests/test_checks.py
git commit -m "feat: add check_usage_tool doctor probe for sigma usage"
```

---

### Task 4: Full regression pass + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass, no failures, no errors.

- [ ] **Step 2: Full ruff check**

Run: `python3 -m ruff check cli/ tests/`
Expected: no errors.

- [ ] **Step 3: Manual end-to-end run (if Node is installed on this machine)**

Run: `which npx || which bunx`

If either is found:

Run: `python3 -m cli.main usage 2>&1 | head -30`
Expected: ccusage's real daily report against this machine's actual `~/.claude/projects/` data (first run may take a few extra seconds to fetch `ccusage@latest` via npx).

If neither is found:

Run: `python3 -m cli.main usage 2>&1`
Expected: prints the `MISSING_NODE_MESSAGE` text, exits 0 — confirm with `echo "exit: $?"`.

- [ ] **Step 4: Confirm `sigma doctor` output includes the new probe**

Run: `python3 -m cli.main doctor 2>&1 | grep -i usage`
Expected: one line referencing the usage/ccusage check, matching whatever OK/WARN state Step 3 implied.

This task produces no commit — verification only.

---

## Self-Review Notes

**Spec coverage check** (against `docs/superpowers/specs/2026-07-07-usage-dashboard-design.md`):
- `node_runtime_available` + `build_argv` in `cli/usage.py` → Task 1.
- `cmd_usage` + `usage` subparser with REMAINDER passthrough → Task 2.
- Fail-safe missing-npx message, exit 0 → Task 2, Step 4 + tests.
- Passthrough exit code from ccusage → Task 2, `test_cmd_usage_passes_through_exit_code`.
- `check_usage_tool` doctor probe, WARN-never-FAIL → Task 3.
- No auto-install of Node/npx (non-goal) → Task 3, Step 2's note explaining `fix=None` is intentional.
- Manual verification against real `~/.claude/projects/` data → Task 4.

All spec sections have a corresponding task. No gaps found.

**Placeholder scan:** no TBD/TODO/"handle appropriately" phrases; every code block is complete.

**Type consistency check:** `node_runtime_available(which: Optional[Callable] = None) -> bool` (Task 1) is called identically in Task 2's `cmd_usage` (no-arg call, uses the real `shutil.which` default) and Task 3's `check_usage_tool` (passes through its own `which` param) — same function, same signature, two call sites, no drift. `build_argv(passthrough_args: List[str]) -> List[str]` (Task 1) is called in Task 2's `cmd_usage` with `list(getattr(args, "usage_args", None) or [])` — matches the `List[str]` parameter type. `Check(name, status, detail, fix=None)` field order in Task 3 matches the existing dataclass definition read from `cli/checks.py` (`name: str, status: str, detail: str, fix: Optional[Fix] = None`).

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-07-usage-dashboard.md`.**
