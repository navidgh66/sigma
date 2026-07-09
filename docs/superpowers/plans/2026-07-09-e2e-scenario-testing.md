# /e2e Executable BDD Scenario Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spec.md's BDD `Scenario:/Given/When/Then` blocks executable — run them live against the target app, gate `sigma loop` cycles on the result, and check them in `/implement-task`, instead of only reasoning about them at review time.

**Architecture:** A new pure module `cli/scenarios.py` parses `Scenario:/Given/When/Then` blocks out of spec.md text (mirrors `cli/eval.py`'s `parse_eval_set`). `cli/loop.py` gains an optional `e2e_runner` axis on `execute_cycle`/`run_loop`, mirroring `logic_checker`'s distinctness + gating shape exactly, with a 3-way verdict (PASS/FAIL/ERROR) instead of the existing 2-way PASS/FAIL. `cli/cost.py` and `cli/main.py` wire routing + a `--e2e` flag the same way `--logic` is wired today. Three command markdown docs (`tasks.md`, new `e2e.md`, `implement-task.md`) carry the plugin-side behavior — no Python backs them.

**Tech Stack:** Python 3.9, pytest, existing `AgentRunner`/`ratchet_to_skills` infra. No new dependencies.

## Global Constraints

- Python 3.9 type hints only (`Optional[X]`, `List[X]` from `typing` — no `X | None`).
- `python3 -m pytest tests/ -q` must stay green after every task.
- `python3 -m ruff check cli/ tests/` must stay clean.
- A bare `execute_cycle(...)`/`run_loop(...)` call with no `e2e_runner`/`make_e2e_runner` must remain byte-identical to current behavior (strict opt-in addition, same law as every other axis).
- `ERROR` is a THIRD verdict state, distinct from `FAIL` — never conflate with the existing 2-way `_verdict_pass`.
- Ratchet only on `FAIL` (real bug), never on `ERROR` (absent evidence) — same law `sigma prune` follows.
- Maker≠checker style distinctness: `e2e_runner` must be `ValueError`-rejected if `is` any of implementer/verifier/logic_checker/test_writer/simplifier/advisor.

---

## File Map

| File | Change |
|---|---|
| `cli/scenarios.py` | **Create.** `Scenario` dataclass + `parse_scenarios()` + `find_scenario()`. |
| `tests/test_scenarios.py` | **Create.** Unit tests for the parser. |
| `cli/loop.py` | **Modify.** `Task.scenarios` field, `TASK_RE` extension, `E2E_PROMPT` constant, `_e2e_verdict()`, `_run_e2e()`, `CycleOutcome.e2e_ok`, `execute_cycle(e2e_runner=...)` wiring, `run_loop(make_e2e_runner=...)` wiring. |
| `tests/test_loop_exec.py` | **Modify.** New tests for the e2e axis. |
| `cli/cost.py` | **Modify.** Add `"e2e": TIER_STRONG` to `routing_for("loop")`. |
| `cli/main.py` | **Modify.** `--e2e` argparse flag + `cmd_loop` wiring + outcome print line. |
| `commands/tasks.md` | **Modify.** Document the Scenarios field per task. |
| `commands/e2e.md` | **Create.** New `/e2e` command template. |
| `commands/implement-task.md` | **Modify.** Add the per-task e2e step after TDD. |

---

### Task 1: `cli/scenarios.py` — parse BDD scenarios out of spec.md

**Files:**
- Create: `cli/scenarios.py`
- Test: `tests/test_scenarios.py`

**Interfaces:**
- Produces: `Scenario` dataclass (`name: str, given: str, when: str, then: str`); `parse_scenarios(spec_md: str) -> List[Scenario]`; `find_scenario(scenarios: List[Scenario], name: str) -> Optional[Scenario]` (case-insensitive exact match on `name`).

The BDD block format already written by `/spec` (see `commands/spec.md`) is:

```gherkin
Scenario: <behavior name>
  Given <starting state / inputs>
  When <action>
  Then <measurable, falsifiable outcome>
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scenarios.py
from cli.scenarios import Scenario, find_scenario, parse_scenarios

SPEC_MD = """
# Spec

## Acceptance criteria

```gherkin
Scenario: user signs up
  Given a new visitor on the signup page
  When they submit a valid email and password
  Then their account is created and they land on the dashboard

Scenario: null input rejected
  Given no input is provided
  When the endpoint is called
  Then a 400 error is returned with a clear message
```

Some other prose that is not a scenario block.
"""


def test_parse_scenarios_extracts_all_blocks():
    scenarios = parse_scenarios(SPEC_MD)
    assert len(scenarios) == 2
    assert scenarios[0] == Scenario(
        name="user signs up",
        given="a new visitor on the signup page",
        when="they submit a valid email and password",
        then="their account is created and they land on the dashboard",
    )
    assert scenarios[1].name == "null input rejected"


def test_parse_scenarios_empty_text_returns_empty_list():
    assert parse_scenarios("") == []
    assert parse_scenarios("# Spec\n\nno scenarios here\n") == []


def test_find_scenario_case_insensitive_exact_match():
    scenarios = parse_scenarios(SPEC_MD)
    found = find_scenario(scenarios, "USER SIGNS UP")
    assert found is not None
    assert found.name == "user signs up"
    assert find_scenario(scenarios, "no such scenario") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_scenarios.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.scenarios'`

- [ ] **Step 3: Write minimal implementation**

```python
# cli/scenarios.py
"""Pure logic for extracting executable BDD scenarios out of spec.md.

`/spec` already writes acceptance criteria as `Scenario:/Given/When/Then`
blocks (see commands/spec.md). This module reads those blocks back out so
`/e2e`, `/implement-task`, and `sigma loop --e2e` can drive them live instead
of only reasoning about them. Mirrors `cli/eval.py`'s `parse_eval_set` shape:
regex-based markdown parsing into a dataclass, no subprocess, no clock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_SCENARIO_RE = re.compile(r"^\s*Scenario:\s*(?P<name>.+?)\s*$")
_GIVEN_RE = re.compile(r"^\s*Given\s+(?P<val>.+?)\s*$", re.IGNORECASE)
_WHEN_RE = re.compile(r"^\s*When\s+(?P<val>.+?)\s*$", re.IGNORECASE)
_THEN_RE = re.compile(r"^\s*Then\s+(?P<val>.+?)\s*$", re.IGNORECASE)


@dataclass
class Scenario:
    name: str
    given: str
    when: str
    then: str


def parse_scenarios(spec_md: str) -> List[Scenario]:
    """Extract every Scenario:/Given/When/Then block from spec.md text.

    Lenient: a Scenario header with a missing Given/When/Then line just leaves
    that field empty rather than dropping the whole block — a partially
    written scenario is still worth surfacing to a human/agent.
    """
    scenarios: List[Scenario] = []
    cur: Optional[dict] = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            scenarios.append(
                Scenario(
                    name=cur["name"],
                    given=cur.get("given", ""),
                    when=cur.get("when", ""),
                    then=cur.get("then", ""),
                )
            )
        cur = None

    for line in spec_md.splitlines():
        header = _SCENARIO_RE.match(line)
        if header:
            flush()
            cur = {"name": header.group("name").strip()}
            continue
        if cur is None:
            continue
        given = _GIVEN_RE.match(line)
        when = _WHEN_RE.match(line)
        then = _THEN_RE.match(line)
        if given:
            cur["given"] = given.group("val")
        elif when:
            cur["when"] = when.group("val")
        elif then:
            cur["then"] = then.group("val")
    flush()
    return scenarios


def find_scenario(scenarios: List[Scenario], name: str) -> Optional[Scenario]:
    """Case-insensitive exact match on scenario name."""
    target = name.strip().lower()
    for s in scenarios:
        if s.name.strip().lower() == target:
            return s
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_scenarios.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add cli/scenarios.py tests/test_scenarios.py
git commit -m "feat: add cli/scenarios.py to parse BDD scenarios from spec.md"
```

---

### Task 2: `cli/loop.py` — `Task.scenarios` field + `TASK_RE` extension

**Files:**
- Modify: `cli/loop.py:17-68` (TASK_RE, Task dataclass, parse_tasks)
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: nothing new (pure regex/dataclass change).
- Produces: `Task.scenarios: List[str]` (scenario names this task maps to, parsed from an inline `[scenario: name]` / `[scenarios: name1, name2]` tag on the task line). Empty list when absent.

Line format: `- [ ] T3 (nlp) [scenario: null input rejected]: validate input` — the tag sits between the domain parens and the trailing `:`. Multiple scenarios: `[scenarios: a, b]` (comma-separated). Both `scenario:` and `scenarios:` singular/plural spellings are accepted (authors will type either).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop.py — add these test functions to the existing file
from cli.loop import parse_tasks


def test_parse_tasks_extracts_scenario_tag():
    md = "- [ ] T3 (nlp) [scenario: null input rejected]: validate input"
    tasks = parse_tasks(md)
    assert tasks[0].scenarios == ["null input rejected"]
    assert tasks[0].title == "validate input"
    assert tasks[0].domain == "nlp"


def test_parse_tasks_extracts_multiple_scenarios():
    md = "- [ ] T4 (mlops) [scenarios: a flow, b flow]: register model"
    tasks = parse_tasks(md)
    assert tasks[0].scenarios == ["a flow", "b flow"]


def test_parse_tasks_no_scenario_tag_defaults_empty():
    md = "- [ ] T1 (nlp): tokenize corpus"
    tasks = parse_tasks(md)
    assert tasks[0].scenarios == []
    assert tasks[0].title == "tokenize corpus"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_loop.py -v -k scenario`
Expected: FAIL — `AttributeError: 'Task' object has no attribute 'scenarios'`

- [ ] **Step 3: Write minimal implementation**

Modify `cli/loop.py` lines 17-68:

```python
# A task line in tasks.md, e.g.:
#   - [ ] T1 (nlp): tokenize corpus
#   - [x] T2 (mlops): register model
#   - [ ] T3 (nlp) [scenario: null input rejected]: validate input
#   - [ ] T4 (mlops) [scenarios: a flow, b flow]: register model
TASK_RE = re.compile(
    r"^\s*-\s*\[(?P<done>[ xX])\]\s*"
    r"(?P<id>[A-Za-z]+\d+)?\s*"
    r"(?:\((?P<domain>[a-z-]+)\))?\s*"
    r"(?:\[\s*scenarios?\s*:\s*(?P<scenarios>[^\]]+)\]\s*)?"
    r":?\s*"
    r"(?P<title>.+?)\s*$"
)


@dataclass
class Task:
    raw: str
    title: str
    done: bool
    id: Optional[str] = None
    domain: Optional[str] = None
    scenarios: List[str] = field(default_factory=list)


@dataclass
class CyclePlan:
    task: Task
    worktree_name: str
    implementer_domain: str
    verifier_domain: str

    def valid_maker_checker(self) -> bool:
        """Maker and checker must be distinct agents (same domain, separate runs)."""
        # Separation is by agent role, not domain; we assert both roles are set.
        return bool(self.implementer_domain) and bool(self.verifier_domain)


def parse_tasks(markdown: str) -> List[Task]:
    """Parse a tasks.md body into Task objects."""
    tasks: List[Task] = []
    for line in markdown.splitlines():
        if "- [" not in line:
            continue
        m = TASK_RE.match(line)
        if not m:
            continue
        raw_scenarios = m.group("scenarios")
        scenarios = (
            [s.strip() for s in raw_scenarios.split(",") if s.strip()]
            if raw_scenarios
            else []
        )
        tasks.append(
            Task(
                raw=line.rstrip(),
                title=m.group("title").strip(),
                done=m.group("done").lower() == "x",
                id=m.group("id"),
                domain=m.group("domain"),
                scenarios=scenarios,
            )
        )
    return tasks
```

Note: `Task` already imports `field` from `dataclasses` (line 11) — no new import needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_loop.py tests/test_loop_exec.py -v`
Expected: PASS (all existing + 3 new tests — the regex change is additive, existing task lines with no `[scenario...]` tag parse identically since the group is optional)

- [ ] **Step 5: Commit**

```bash
git add cli/loop.py tests/test_loop.py
git commit -m "feat: add Task.scenarios field parsed from tasks.md [scenario: ...] tag"
```

---

### Task 3: `cli/loop.py` — e2e prompt constant + 3-way verdict parser

**Files:**
- Modify: `cli/loop.py` (add after `ADVISOR_RETRY_PREFIX`, before `CycleOutcome`)
- Test: `tests/test_loop_exec.py`

**Interfaces:**
- Consumes: `Scenario` from `cli/scenarios.py` (Task 1).
- Produces: `E2E_PROMPT` (str template with `{domain}`, `{title}`, `{scenario_name}`, `{given}`, `{when}`, `{then}` placeholders); `_e2e_verdict(output: str) -> str` returning `"PASS"`, `"FAIL"`, or `"ERROR"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop_exec.py — add near test_verdict_pass_parsing
from cli.loop import _e2e_verdict


def test_e2e_verdict_pass():
    assert _e2e_verdict("ran the flow\nVERDICT: PASS") == "PASS"


def test_e2e_verdict_fail():
    assert _e2e_verdict("assertion did not hold\nVERDICT: FAIL") == "FAIL"


def test_e2e_verdict_error_explicit():
    assert _e2e_verdict("could not reach app\nVERDICT: ERROR") == "ERROR"


def test_e2e_verdict_defaults_to_error_when_missing():
    # Inconclusive-by-default: an agent that crashed/timed out produced no real
    # verdict at all — categorically different from a clean run that FAILed.
    assert _e2e_verdict("garbled output, no verdict line") == "ERROR"
    assert _e2e_verdict("") == "ERROR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k e2e_verdict`
Expected: FAIL — `ImportError: cannot import name '_e2e_verdict' from 'cli.loop'`

- [ ] **Step 3: Write minimal implementation**

Add to `cli/loop.py` immediately after the `ADVISOR_RETRY_PREFIX` constant (before the `@dataclass class CycleOutcome` block):

```python
# E2E axis: a DISTINCT agent drives the task's mapped BDD scenario(s) live
# (Given/When) and checks the Then assertion against a running instance of the
# target app, instead of just reasoning about the code. Three-way verdict —
# PASS/FAIL/ERROR — because "could not reach the app" is categorically
# different from "ran cleanly and the assertion was false": an ERROR must
# never gate a cycle the same way a real behavioral FAIL does (see
# `_e2e_verdict`'s ERROR-by-default parsing below).
E2E_PROMPT = (
    "You are the E2E RUNNER — a distinct agent from the implementer, checker, "
    "logic evaluator, test writer, simplifier, and advisor. Drive this BDD "
    "scenario LIVE against a running instance of the app (launch it via the "
    "`run` skill if it is not already up) using whatever tool fits — browser "
    "automation for a web UI, HTTP calls for an API, subprocess invocation for "
    "a CLI. Do NOT fabricate a result: if you cannot complete Given/When (app "
    "unreachable, tool crash, timeout), that is an ERROR, not a PASS or FAIL.\n"
    "Domain: {domain}\nTask: {title}\n\n"
    "Scenario: {scenario_name}\n"
    "Given {given}\n"
    "When {when}\n"
    "Then {then}\n\n"
    "Perform Given and When for real, then check whether Then actually holds. "
    "Reply with a final line exactly one of:\n"
    "VERDICT: PASS   (ran to completion, Then held)\n"
    "VERDICT: FAIL   (ran to completion, Then's assertion was false)\n"
    "VERDICT: ERROR  (could not complete Given/When — inconclusive)"
)


def _e2e_verdict(output: str) -> str:
    """Parse the e2e runner's 3-way verdict line.

    Unlike `_verdict_pass` (2-way, defaults to FAIL — skeptical on a real
    assertion), this defaults to ERROR when no VERDICT line is found: a
    crashed/timed-out/garbled run produced no real verdict at all, which must
    never be scored as a behavioral FAIL (that would ratchet a lesson from
    absent evidence — the same law `sigma prune` follows for unused-tool
    evidence).
    """
    for line in reversed(output.splitlines()):
        s = line.strip().upper()
        if s.startswith("VERDICT:"):
            if "PASS" in s:
                return "PASS"
            if "FAIL" in s:
                return "FAIL"
            return "ERROR"
    return "ERROR"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k e2e_verdict`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: add E2E_PROMPT and 3-way _e2e_verdict parser to loop.py"
```

---

### Task 4: `cli/loop.py` — `CycleOutcome.e2e_ok` + `_run_e2e` helper + `execute_cycle` wiring

**Files:**
- Modify: `cli/loop.py` (`CycleOutcome` dataclass, new `_run_e2e` function, `execute_cycle` signature + body)
- Test: `tests/test_loop_exec.py`

**Interfaces:**
- Consumes: `Scenario`/`find_scenario` from `cli/scenarios.py`; `E2E_PROMPT`/`_e2e_verdict` from Task 3; `plan.task.scenarios: List[str]` from Task 2.
- Produces: `CycleOutcome.e2e_ok: Optional[bool]`; `_run_e2e(plan, workspace, e2e_runner, spec_scenarios, recall, cwd=None) -> tuple` returning `(status, reason, detail)` where `status` is one of `"pass"`, `"fail"`, `"error"`, `"skipped"` (skipped = task has no mapped scenario, or the scenario name isn't found in spec.md); `execute_cycle(..., e2e_runner=None, spec_scenarios=None, ...)`.

**Design decisions locked in:**
- `_run_e2e` runs AFTER `_run_verify`/advisor-escalation resolve `passed=True` — an e2e check on code that already failed verify is wasted work.
- `spec_scenarios: Optional[List[Scenario]]` is a new `execute_cycle` param (the caller — `run_loop`/`cmd_loop` — reads spec.md once and passes the parsed list down; `execute_cycle` itself never touches the filesystem for spec.md, staying consistent with "pure logic reads what it's given").
- Gate semantics: `status == "fail"` → `outcome.verified = False`, ratchets via `ratchet_to_skills(skills_dir, f"e2e failed: {title}", reason, domain)` (distinct prefix from `"verify failed:"` for clearer provenance in the ratcheted SKILL.md — confirmed safe: `cli/skills_index.py`'s `_NOISE_PREFIXES` list doesn't need `"e2e failed:"` added, because two DIFFERENT prefixes on the SAME topic already share a `topic_key` after either prefix is stripped only if it's IN the list — since `"e2e failed:"` is NOT in `_NOISE_PREFIXES`, a lesson titled `"e2e failed: validate input"` gets `topic_key` = `"e2e-failed-validate-input"`, NOT colliding with a `"verify failed: validate input"` lesson's key `"validate-input"`. This is the correct behavior for this feature: an e2e failure and a verify failure on the same task are DIFFERENT lessons (one's a live behavioral bug, one's a code-quality issue) and should NOT be flagged as contradicting each other just because they share a task title. No change needed to `skills_index.py`.)
- `status == "error"` → does NOT flip `outcome.verified`, does NOT ratchet, appends a note.
- `status == "skipped"` → `outcome.e2e_ok` stays `None`, nothing else happens.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_loop_exec.py — add a new section after the advisor tests
from cli.scenarios import Scenario

E2E_TASKS = """
- [ ] T1 (nlp) [scenario: happy path]: build the flow
"""


def test_e2e_runner_must_be_distinct(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    with pytest.raises(ValueError):
        execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, e2e_runner=impl)


def test_e2e_pass_keeps_cycle_passing(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="drove it\nVERDICT: PASS")])
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=scenarios,
    )
    assert out.verified is True
    assert out.e2e_ok is True
    assert out.ratcheted_skill is None


def test_e2e_fail_blocks_and_ratchets(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="assertion false\nVERDICT: FAIL")])
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=scenarios,
    )
    assert out.verified is False
    assert out.e2e_ok is False
    assert out.ratcheted_skill is not None
    assert out.ratcheted_skill.exists()
    assert "e2e failed" in out.ratcheted_skill.read_text().lower()


def test_e2e_error_does_not_block_or_ratchet(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="app unreachable\nVERDICT: ERROR")])
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=scenarios,
    )
    assert out.verified is True          # ERROR never flips a pass to fail
    assert out.e2e_ok is None            # inconclusive, not a scored False
    assert out.ratcheted_skill is None   # no lesson from absent evidence
    assert any("e2e error" in n.lower() for n in out.notes)


def test_e2e_skipped_when_no_mapped_scenario(tmp_path):
    # Task has NO [scenario: ...] tag — e2e_runner is given but must not run.
    tasks = parse_tasks(TASKS)  # the plain fixture from the top of this file
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="should not run")])
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=[],
    )
    assert out.verified is True
    assert out.e2e_ok is None
    assert e2e.prompts == []  # never called


def test_e2e_skipped_when_scenario_name_not_found_in_spec(tmp_path):
    # Task references a scenario name that isn't in the (parsed) spec — treat
    # as skipped, same as no mapping (fail-safe: a typo'd/renamed scenario
    # name never silently gates a cycle on nothing).
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="should not run")])
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=[],  # "happy path" not present
    )
    assert out.e2e_ok is None
    assert e2e.prompts == []


def test_e2e_not_called_on_verify_fail(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: FAIL")])
    e2e = ScriptedRunner([AgentResult(ok=True, output="should not run")])
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=scenarios,
    )
    assert out.verified is False
    assert out.e2e_ok is None
    assert e2e.prompts == []


def test_advisor_escalates_on_e2e_fail(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([
        AgentResult(ok=True, output="implemented v1"),
        AgentResult(ok=True, output="implemented v2 (advisor retry)"),
    ])
    chk = ScriptedRunner([
        AgentResult(ok=True, output="VERDICT: PASS"),   # initial verify passes
        AgentResult(ok=True, output="VERDICT: PASS"),   # re-verify after retry passes
    ])
    e2e = ScriptedRunner([
        AgentResult(ok=True, output="assertion false\nVERDICT: FAIL"),  # first e2e fails
        AgentResult(ok=True, output="drove it\nVERDICT: PASS"),         # e2e after retry passes
    ])
    advisor = ScriptedRunner([AgentResult(ok=True, output="1. fix X\nRoot cause: X")])
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    out = execute_cycle(
        plan, tmp_path, tmp_path / "skills", impl, chk,
        e2e_runner=e2e, spec_scenarios=scenarios,
        advisor=advisor, advisor_rounds=1,
    )
    assert out.verified is True
    assert out.advised is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k "e2e"`
Expected: FAIL — `TypeError: execute_cycle() got an unexpected keyword argument 'e2e_runner'`

- [ ] **Step 3: Write minimal implementation**

Modify `CycleOutcome` (add field after `contradiction`):

```python
@dataclass
class CycleOutcome:
    task_title: str
    implemented: bool
    verified: bool
    logic_ok: Optional[bool] = None
    test_written: Optional[bool] = None  # set only in TDD mode
    regression_test: Optional[Path] = None  # TDD: test pinning a verify-fail bug
    simplified: Optional[bool] = None  # set only in --simplify mode: did cleanup stick?
    advised: Optional[bool] = None  # set only in --advisor mode: did escalation rescue the cycle?
    advisor_rounds_used: Optional[int] = None  # set only in --advisor mode
    merge_conflict: Optional[Path] = None  # --team + worktrees: set when a PASSing cycle's merge conflicts
    ratcheted_skill: Optional[Path] = None
    contradiction: Optional[Path] = None
    # set only when the task has a mapped scenario found in spec_scenarios and
    # e2e_runner was given: True=PASS, False=FAIL (blocks+ratchets), None=no
    # mapped scenario OR e2e ERROR (inconclusive, never blocks/ratchets).
    e2e_ok: Optional[bool] = None
    notes: List[str] = field(default_factory=list)
```

Add `_run_e2e` right after `_run_verify` (before `_run_advisor_escalation`):

```python
def _run_e2e(
    plan: CyclePlan,
    workspace: Path,
    e2e_runner: Optional[AgentRunner],
    spec_scenarios: Optional[List["Scenario"]],
    recall: str,
    cwd: Optional[Path] = None,
) -> tuple:
    """Run the mapped scenario(s) live. Returns (status, reason, detail).

    `status` is one of "skipped" (no e2e_runner, no mapped scenario name, or
    the name isn't found in `spec_scenarios`), "pass", "fail", "error". Only
    the FIRST mapped scenario name on the task is run (today's scope: one
    scenario per task keeps this a per-task gate, not a full-suite re-run —
    `/e2e` itself covers running every scenario in spec.md). `reason`/`detail`
    mirror `_run_verify`'s shape so `_run_advisor_escalation` composes with
    this axis unmodified.
    """
    from cli.scenarios import find_scenario

    if e2e_runner is None or not plan.task.scenarios or not spec_scenarios:
        return "skipped", "", ""
    scenario = find_scenario(spec_scenarios, plan.task.scenarios[0])
    if scenario is None:
        return "skipped", "", ""

    cwd = cwd if cwd is not None else workspace
    title = plan.task.title
    domain = plan.implementer_domain
    result = e2e_runner.run(
        _with_recall(
            E2E_PROMPT.format(
                domain=domain,
                title=title,
                scenario_name=scenario.name,
                given=scenario.given,
                when=scenario.when,
                then=scenario.then,
            ),
            recall,
        ),
        cwd=cwd,
        role="e2e",
    )
    write_artifact(workspace / "e2e" / f"{plan.worktree_name}.md", result.output)
    if not result.ok:
        return "error", result.error or "e2e runner crashed", result.output

    verdict = _e2e_verdict(result.output)
    if verdict == "PASS":
        return "pass", "", ""
    if verdict == "FAIL":
        return "fail", f"e2e scenario '{scenario.name}' failed", result.output
    return "error", f"e2e scenario '{scenario.name}' inconclusive", result.output
```

Modify `execute_cycle`'s signature and distinctness checks:

```python
def execute_cycle(
    plan: CyclePlan,
    workspace: Path,
    skills_dir: Path,
    implementer: AgentRunner,
    verifier: AgentRunner,
    logic_checker: Optional[AgentRunner] = None,
    recall: str = "",
    test_writer: Optional[AgentRunner] = None,
    simplifier: Optional[AgentRunner] = None,
    advisor: Optional[AgentRunner] = None,
    advisor_rounds: int = 1,
    agent_cwd: Optional[Path] = None,
    e2e_runner: Optional[AgentRunner] = None,
    spec_scenarios: Optional[List["Scenario"]] = None,
) -> CycleOutcome:
```

(docstring: add a paragraph before the final `agent_cwd`/`recall` paragraphs)

```python
    When `e2e_runner` is provided AND the task has a mapped scenario found in
    `spec_scenarios`, a distinct agent drives that scenario live AFTER verify
    (+logic) pass, gating the cycle: FAIL blocks + ratchets (same law as a
    verify/logic FAIL); ERROR (couldn't complete Given/When — inconclusive)
    does NOT flip an otherwise-passing cycle to FAIL and is never ratcheted.
    No mapped scenario → skipped entirely, `CycleOutcome.e2e_ok` stays None.
```

Extend the distinctness-check chain (add after the `advisor` check, before `cwd = agent_cwd if ...`):

```python
    if e2e_runner is not None and (
        e2e_runner is implementer
        or e2e_runner is verifier
        or e2e_runner is logic_checker
        or e2e_runner is test_writer
        or e2e_runner is simplifier
        or e2e_runner is advisor
    ):
        raise ValueError(
            "e2e runner must be distinct from maker, checker, logic, test, "
            "simplifier, and advisor agents"
        )
```

Wire the e2e gate into the pass/fail flow. Replace the block starting at `if passed:` / `else:` (the final branch of `execute_cycle`) with:

```python
    if passed:
        e2e_status, e2e_reason, e2e_detail = _run_e2e(
            plan, workspace, e2e_runner, spec_scenarios, recall, cwd=cwd
        )
        if e2e_status == "pass":
            outcome.e2e_ok = True
        elif e2e_status == "error":
            outcome.e2e_ok = None
            outcome.notes.append(f"e2e error: {e2e_reason}")
            append_loop_log(workspace, f"{title}: e2e ERROR ({e2e_reason}) — cycle stands")
        elif e2e_status == "fail":
            outcome.e2e_ok = False
            passed = False
            outcome.verified = False
            reason, detail = e2e_reason, e2e_detail
        # "skipped": outcome.e2e_ok stays None, no notes, nothing else changes.

    if passed:
        append_loop_log(workspace, f"{title}: PASS")
        # Anti-slop cleanup runs ONLY after a pass (it polishes verified code, it
        # is not a gate). A distinct simplifier refines for clarity; the verifier
        # then re-checks to confirm behaviour was preserved — a regression reverts
        # the simplify, never the feature. Best-effort: a failed simplify is logged
        # and the (already-passing) cycle stands.
        if simplifier is not None:
            _run_simplify(plan, workspace, simplifier, verifier, outcome)
    else:
        outcome.notes.append(f"verify failed: {reason}" if outcome.e2e_ok is None or outcome.e2e_ok else f"e2e failed: {reason}")
        ratchet_title = f"e2e failed: {title}" if outcome.e2e_ok is False else f"verify failed: {title}"
        outcome.ratcheted_skill = ratchet_to_skills(
            skills_dir, ratchet_title, reason, domain
        )
        outcome.contradiction = _contradiction_flag(skills_dir, outcome.ratcheted_skill)
        append_loop_log(workspace, f"{title}: {'e2e' if outcome.e2e_ok is False else 'verify'} FAILED ({reason})")
        # TDD: pin the bug with a regression test so the loop can never silently
        # regress on it. Best-effort — a failed write is logged, never fatal.
        if test_writer is not None:
            reg = test_writer.run(
                REGRESSION_PROMPT.format(domain=domain, title=title, reason=reason),
                cwd=workspace,
                role="test-writer",
            )
            if reg.ok:
                outcome.regression_test = write_artifact(
                    workspace / "regressions" / f"{plan.worktree_name}.md", reg.output
                )
                append_loop_log(workspace, f"{title}: regression test pinned")
            else:
                outcome.notes.append(f"regression-test write failed: {reg.error}")
    return outcome
```

This reuses `outcome.e2e_ok is False` as the discriminator for which ratchet title/log text to use, since `_run_e2e` only sets `passed = False` (triggering the `else` branch) when `e2e_status == "fail"` — a plain verify/logic FAIL never touches `outcome.e2e_ok` (it stays at its initial `None`), so the `else` branch's `outcome.e2e_ok is False` check correctly distinguishes "verify/logic failed" from "e2e failed" without a separate flag.

Add the import at the top of `cli/loop.py` (inside the `TYPE_CHECKING`-free existing import block — `Scenario` is only used in a type-hint position and inside `_run_e2e`'s local import, so no top-level circular-import risk):

```python
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from cli.scenarios import Scenario
```

(Replace the existing `from typing import Dict, List, Optional` line at the top of the file with this two-line form.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_loop_exec.py -v`
Expected: PASS (all existing tests + 8 new e2e tests)

- [ ] **Step 5: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: add e2e_runner gate axis to execute_cycle (FAIL blocks, ERROR doesn't)"
```

---

### Task 5: `cli/loop.py` — `run_loop` wiring for `make_e2e_runner` + spec_scenarios

**Files:**
- Modify: `cli/loop.py:762-897` (`run_loop` signature, `run_one`)
- Test: `tests/test_loop_exec.py`

**Interfaces:**
- Consumes: `execute_cycle(e2e_runner=..., spec_scenarios=...)` from Task 4.
- Produces: `run_loop(..., make_e2e_runner=None, spec_scenarios=None, ...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop_exec.py
from cli.scenarios import Scenario


def test_run_loop_with_e2e_runner(tmp_path):
    tasks = parse_tasks(E2E_TASKS)
    scenarios = [Scenario(name="happy path", given="g", when="w", then="t")]
    outcomes = run_loop(
        tasks,
        tmp_path,
        tmp_path / "skills",
        max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        make_e2e_runner=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        spec_scenarios=scenarios,
    )
    assert len(outcomes) == 1
    assert outcomes[0].verified is True
    assert outcomes[0].e2e_ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_loop_exec.py -v -k test_run_loop_with_e2e_runner`
Expected: FAIL — `TypeError: run_loop() got an unexpected keyword argument 'make_e2e_runner'`

- [ ] **Step 3: Write minimal implementation**

Modify `run_loop`'s signature (add two new params after `advisor_rounds`):

```python
def run_loop(
    tasks: List[Task],
    workspace: Path,
    skills_dir: Path,
    max_cycles: int,
    make_implementer,
    make_verifier,
    make_logic_checker=None,
    gate: Optional[str] = None,
    make_test_writer=None,
    make_simplifier=None,
    make_advisor=None,
    advisor_rounds: int = 1,
    make_e2e_runner=None,
    spec_scenarios: Optional[List["Scenario"]] = None,
    team: bool = False,
    max_workers: int = 3,
    worktrees: bool = True,
    project_root: Optional[Path] = None,
) -> List[CycleOutcome]:
```

Add a docstring paragraph after the advisor paragraph:

```python
    `make_e2e_runner`, when provided, adds a distinct agent that drives each
    task's mapped BDD scenario live (see `execute_cycle`'s e2e axis).
    `spec_scenarios` is the parsed list of Scenario blocks from spec.md (read
    once by the caller, e.g. `cmd_loop`) — a task with no mapped scenario, or
    one whose scenario name isn't in this list, skips the e2e axis entirely.
```

Modify `run_one`:

```python
    def run_one(task: Task, agent_cwd: Optional[Path] = None) -> CycleOutcome:
        plan = plan_cycle(task)
        return execute_cycle(
            plan, workspace, skills_dir,
            make_implementer(), make_verifier(),
            make_logic_checker() if make_logic_checker else None,
            recall=recall_cache.get(plan.implementer_domain, ""),
            test_writer=make_test_writer() if make_test_writer else None,
            simplifier=make_simplifier() if make_simplifier else None,
            advisor=make_advisor() if make_advisor else None,
            advisor_rounds=advisor_rounds,
            agent_cwd=agent_cwd,
            e2e_runner=make_e2e_runner() if make_e2e_runner else None,
            spec_scenarios=spec_scenarios,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_loop_exec.py -v`
Expected: PASS (all tests, including the new `test_run_loop_with_e2e_runner`)

- [ ] **Step 5: Commit**

```bash
git add cli/loop.py tests/test_loop_exec.py
git commit -m "feat: wire make_e2e_runner + spec_scenarios through run_loop"
```

---

### Task 6: `cli/cost.py` — `e2e` routing tier

**Files:**
- Modify: `cli/cost.py:94-100` (`routing_for("loop")`)
- Test: `tests/test_cost.py` (check this file exists first; if not, create it minimally for this one test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `routing_for("loop")["e2e"] == "opus"` (TIER_STRONG).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cost.py — add this test (create the file with this content if it
# doesn't exist yet; if it exists, just add the function)
from cli.cost import TIER_STRONG, routing_for


def test_loop_routing_includes_e2e_at_strong_tier():
    routes = routing_for("loop")
    assert routes["e2e"] == TIER_STRONG
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cost.py -v -k e2e`
Expected: FAIL — `KeyError: 'e2e'`

- [ ] **Step 3: Write minimal implementation**

Modify `cli/cost.py`'s `routing_for`:

```python
    if op == "loop":
        return {
            "implement": TIER_MID,
            "verify": TIER_MID,
            "logic": TIER_STRONG,
            "advisor": TIER_STRONG,
            "e2e": TIER_STRONG,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cost.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/cost.py tests/test_cost.py
git commit -m "feat: route the e2e loop axis to the strong model tier"
```

---

### Task 7: `cli/main.py` — `--e2e` flag + `cmd_loop` wiring

**Files:**
- Modify: `cli/main.py:120-246` (`cmd_loop`), `cli/main.py:840-866` (loop argparse block)

**Interfaces:**
- Consumes: `run_loop(make_e2e_runner=..., spec_scenarios=...)` from Task 5; `routing_for("loop")["e2e"]` from Task 6; `cli.scenarios.parse_scenarios` from Task 1.
- Produces: `sigma loop --e2e` CLI flag.

No dedicated unit test for `cmd_loop` itself exists in the test suite today (it's the CLI wiring layer — verified by the manual dry-run steps below, consistent with how `--logic`/`--simplify`/`--advisor` were verified when added).

- [ ] **Step 1: Add the argparse flag**

Modify `cli/main.py` lines 840-866, inserting after the `--advisor-rounds` line:

```python
    pl.add_argument("--advisor-rounds", type=int, default=1,
                    help="max advisor→retry→re-verify rounds per cycle before ratcheting (default 1)")
    pl.add_argument("--e2e", action="store_true",
                    help="drive each task's mapped BDD scenario live (Given/When/Then) after "
                         "verify+logic pass; a real behavioral FAIL blocks the cycle, an ERROR "
                         "(app unreachable) does not")
    pl.add_argument("--keep-awake", action="store_true", help="prevent Mac sleep during the run (caffeinate)")
```

- [ ] **Step 2: Wire it into `cmd_loop`**

Modify `cli/main.py`'s `cmd_loop` (around line 165, add after the `--simplify` print block):

```python
    if args.simplify:
        _print("  🧹 simplify mode: a distinct agent cleans up slop after each pass (re-verified)")
    if args.e2e:
        _print("  🌐 e2e mode: a distinct agent drives each task's mapped BDD scenario live "
                "(FAIL blocks, ERROR doesn't)")
    if args.advisor:
```

Add the spec.md scenario parse + `make_e2e_runner` factory (around line 197, after `advisor_model = ...`):

```python
    advisor_model = args.model_advisor or routes.get("advisor") or "opus"

    # e2e axis: parse spec.md's BDD scenarios ONCE up front (spec_scenarios is
    # a plain list passed to every cycle — execute_cycle never re-reads the
    # file). Missing spec.md → empty list (fail-safe: every task's e2e step
    # simply skips, same as having no mapped scenario).
    spec_scenarios = []
    if args.e2e:
        from cli.scenarios import parse_scenarios

        spec_file = ws / "spec.md"
        if spec_file.exists():
            spec_scenarios = parse_scenarios(spec_file.read_text())
        else:
            _print(f"  ⚠ --e2e given but no spec.md at {spec_file} — every task's e2e step will skip")
```

Modify the `run_loop(...)` call (around line 203-219):

```python
    with keep_awake(enabled=args.keep_awake):
        outcomes = run_loop(
            tasks,
            ws,
            skills_dir,
            cfg.loop.max_cycles,
            make_implementer=lambda: _make(routes.get("implement")),
            make_verifier=lambda: _make(routes.get("verify")),
            make_logic_checker=(lambda: _make(routes.get("logic"))) if args.logic else None,
            make_test_writer=(lambda: _make(routes.get("verify"))) if args.tdd else None,
            make_simplifier=(lambda: _make(routes.get("implement"))) if args.simplify else None,
            make_advisor=(lambda: _make(advisor_model)) if args.advisor else None,
            advisor_rounds=args.advisor_rounds,
            make_e2e_runner=(lambda: _make(routes.get("e2e"))) if args.e2e else None,
            spec_scenarios=spec_scenarios if args.e2e else None,
            team=args.team,
            worktrees=cfg.loop.worktrees,
            project_root=project_root(),
            gate=args.gate,
        )
```

Add the outcome-print line (around line 236, after the `simplified` print block):

```python
        if o.simplified is not None:
            _print(f"    simplify: {'✓ applied (re-verified)' if o.simplified else '✗ skipped/reverted'}")
        if o.e2e_ok is not None:
            _print(f"    e2e: {'✓ passed' if o.e2e_ok else '✗ failed (blocked)'}")
        if o.advised is not None:
```

- [ ] **Step 3: Manual verification (no unit test for CLI wiring)**

Run: `python3 -m cli.main loop --help`
Expected: output includes the `--e2e` flag with its help text.

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass (no regressions from the main.py edit — it has no direct unit test, but the full suite catches import errors).

- [ ] **Step 4: Commit**

```bash
git add cli/main.py
git commit -m "feat: wire --e2e flag through sigma loop"
```

---

### Task 8: `commands/tasks.md` — document the Scenarios field

**Files:**
- Modify: `commands/tasks.md`

- [ ] **Step 1: Edit the file**

Replace the `## Behavior` section's task bullet list (currently ID/Domain/Pre-discovered context/Acceptance criteria/Dependencies) to add a Scenarios line, and document the line-format convention:

```markdown
## Behavior

1. Read `spec.md`.
2. Produce `tasks.md` — an ordered, checkbox task list. For each task:
   - ID + title
   - **Domain** (which `sigma` context-engine implements it:
     classic-ml / deep-learning / nlp / rl / data-analysis /
     data-engineering / ai-agent-engineering / mlops / llm-engineering)
   - **Scenarios** — the exact `spec.md` `Scenario:` name(s) this task must
     satisfy, as an inline tag on the task line: `[scenario: <name>]` for one,
     `[scenarios: <name1>, <name2>]` for several. Leave the tag off entirely
     for tasks with no user-facing flow (e.g. a pure backend utility) — not
     every task maps to a scenario. Example:
     `- [ ] T3 (nlp) [scenario: null input rejected]: validate input`
   - Pre-discovered context (files, interfaces it touches)
   - Acceptance criteria for that task
   - Dependencies (which tasks must precede it)
3. Mark which tasks can run in **parallel** (no shared state).

## Rules

- Each task is independently implementable and verifiable.
- Right granularity — not too big, not trivial.
- Surface ordering and dependencies explicitly.
- A task whose scenario tag names something not present in `spec.md` is a
  spec/tasks mismatch — fix the tag or the spec before proceeding.

## Next

→ `/implement-task <id>` or `/loop` (pass `--e2e` to gate cycles on each
task's mapped scenario running live)
```

- [ ] **Step 2: Commit**

```bash
git add commands/tasks.md
git commit -m "docs: document the Scenarios field in /tasks output"
```

---

### Task 9: `commands/e2e.md` — new `/e2e` command

**Files:**
- Create: `commands/e2e.md`

- [ ] **Step 1: Write the file**

```markdown
---
command: /e2e
description: Run spec.md's BDD scenarios end-to-end against a live instance of the target app
stage: aux
inputs: ["sigma/specs/{date}-{slug}/spec.md"]
outputs: ["sigma/specs/{date}-{slug}/e2e-report.md"]
---

# /e2e

Run every **Scenario / Given / When / Then** block in `spec.md` **live**
against a running instance of the target app — not just reasoning about the
code, actually driving it.

## Behavior

1. Resolve the workspace: no argument → the most recently modified
   `sigma/specs/{date}-{slug}/` directory containing a `spec.md`.
2. Extract every `Scenario:/Given/When/Then` block from `spec.md`.
3. **Launch the app** — invoke the `run` skill (it detects whether the app is
   already live and starts it if not).
4. For each scenario, perform **Given** (starting state) and **When** (the
   action) using whatever tool fits: browser automation for a web UI, HTTP
   calls for an API, subprocess invocation for a CLI. Then check **Then** and
   assign a verdict:
   - `PASS` — ran to completion, Then held.
   - `FAIL` — ran to completion, Then's assertion was false. A real behavior
     bug.
   - `ERROR` — could not complete Given/When (app unreachable, tool crash,
     timeout). Inconclusive — NOT a behavior verdict.
5. Write `sigma/specs/{date}-{slug}/e2e-report.md`: one row per scenario —
   name | verdict | evidence (screenshot ref / response body / stdout
   excerpt) — plus an overall summary.
6. **Ratchet**: every `FAIL` (never `ERROR` — no lesson from absent evidence)
   writes a lesson via the exact `/sigma-learn-lesson` format (domain-tagged),
   so `sigma loop --e2e` and `/implement-task` recall it next time.

## Report format

```markdown
# E2E Report — {workspace slug}

| Scenario | Verdict | Evidence |
|---|---|---|
| user signs up | PASS | screenshot: signup-success.png |
| null input rejected | FAIL | expected 400, got 500 — see response.json |
| dependency unavailable | ERROR | app unreachable on :3000 after 30s |

**Summary:** 1 PASS / 1 FAIL / 1 ERROR — not clean.
```

## Rules

- One agent per scenario drives Given/When AND checks Then — no actor/judge
  split (mirrors how a human tester works a scenario end to end).
- Never fabricate a PASS. An incomplete Given/When is ERROR, not a guess.
- Ratchet FAIL only — an ERROR is absent evidence, not a lesson.

## Next

→ all PASS: ship · any FAIL: fix impl (lesson ratcheted), re-run `/e2e` · any
ERROR: fix the environment, re-run.
```

- [ ] **Step 2: Commit**

```bash
git add commands/e2e.md
git commit -m "feat: add /e2e command — run spec.md BDD scenarios live"
```

---

### Task 10: `commands/implement-task.md` — per-task e2e step

**Files:**
- Modify: `commands/implement-task.md`

- [ ] **Step 1: Edit the file**

Add a new numbered step after the existing implementation step (the one that says "Write a short `impl/{task_id}.md` note...") and before the `## TDD mode` section header:

```markdown
5. Write a short `impl/{task_id}.md` note: what changed, why, which scenarios
   it satisfies, how to verify.

## E2E scenario check — if this task has a mapped Scenario

If `tasks.md` tags this task with `[scenario: <name>]` (or `scenarios:`),
run that scenario end-to-end the same way `/e2e` does: launch the app via the
`run` skill if it isn't already live, drive Given/When for real, check Then,
and record the verdict in `impl/{task_id}.md`.

- `PASS` — proceed to `/verify`.
- `FAIL` — the task is **not actually done**. Do not consider it complete
  until the scenario passes. Fix the implementation and re-run this check.
- `ERROR` — an environment issue (app unreachable, tool crash), not a
  behavior bug. Note it and retry before moving to `/verify`; do not block
  completion on an ERROR the way a FAIL blocks it.

This runs the mapped scenario ONCE for this task — not the full spec suite
(that's what `/e2e` is for).

## TDD mode — when asked to "do it test-first" / "TDD"
```

- [ ] **Step 2: Commit**

```bash
git add commands/implement-task.md
git commit -m "docs: add per-task e2e scenario check to /implement-task"
```

---

## Final Verification

- [ ] **Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass (was 756 before this plan; +3 scenarios tests +3 Task.scenarios tests +4 e2e_verdict tests +8 e2e-axis tests +1 run_loop test +1 cost test = +20, so ~776).

- [ ] **Run lint**

Run: `python3 -m ruff check cli/ tests/`
Expected: clean.

- [ ] **Manual dry-run of the CLI wiring**

Run: `python3 -m cli.main loop --help | grep -A2 -- --e2e`
Expected: shows the `--e2e` flag and its help text.

---

## Self-Review

**1. Spec coverage** — every design-doc surface has a task:
- Surface 1 (`tasks.md` Scenarios field) → Task 2 (parsing) + Task 8 (docs).
- Surface 2 (`/e2e` command) → Task 9.
- Surface 3 (`/implement-task` step) → Task 10.
- Surface 4 (`loop.py` gate axis + cost.py + main.py) → Tasks 1, 3, 4, 5, 6, 7.

**2. Placeholder scan** — no TBD/TODO; every step has complete code; no
"similar to Task N" (each task's code block is fully written out, including
the near-duplicate `_run_e2e`/`_run_verify` shapes, because `execute_cycle`'s
implementer reads tasks independently).

**3. Type/signature consistency** — `Scenario(name, given, when, then)` used
identically in Tasks 1, 3, 4, 5. `_e2e_verdict(output: str) -> str` returns
exactly `"PASS"`/`"FAIL"`/`"ERROR"` everywhere it's consumed (Task 4's
`_run_e2e`). `CycleOutcome.e2e_ok: Optional[bool]` semantics (`True`/`False`/
`None`) match across Task 4's implementation and its tests. `run_loop`'s new
params (`make_e2e_runner`, `spec_scenarios`) match `execute_cycle`'s
(`e2e_runner`, `spec_scenarios`) in Task 5. `routing_for("loop")["e2e"]`
(Task 6) is consumed by `routes.get("e2e")` in Task 7 — key name matches.
