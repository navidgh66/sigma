# Orchestration Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route hermes pipeline stages by tier (planning/grill → strong, execution → mid) and consume the dead `routing_for("research")["synthesis"]` key, so top-tier models do the reasoning work and mid-tier models execute — matching the loop's existing routing philosophy.

**Architecture:** Extend `cost.routing_for` with a `"hermes"` per-stage map. `run_hermes` gains an optional `stage_routes` dict and resolves the execution runner's model AFTER the route picks the stage (the intent-classification runner stays unrouted — it's cheap). Research synthesis gets a routed runner factory built on a new `model_alias` passthrough in the claude adapter. Both commands default routed with `--no-route` opt-out, mirroring `sigma loop`.

**Tech Stack:** Python 3.9, stdlib only, pytest, ruff.

## Global Constraints

- Python 3.9 type hints: `Optional[X]`, `List[X]`, `Dict[K, V]` from `typing` — NEVER `X | None` (ruff `UP` intentionally disabled).
- Prompts/args pass via argv, never the shell.
- All 872 existing test functions must stay green: `python3 -m pytest tests/ -q`.
- Lint after every task: `python3 -m ruff check cli/ tests/`.
- Backwards compat: a `make_runner` factory taking zero args (existing tests) must keep working; `run_model`/`build_argv` callers without the new kwarg must be byte-identical in behavior.
- Attribution disabled globally — commit messages have NO Co-Authored-By trailer.
- Final task bumps version in BOTH `cli/__init__.py` and `.claude-plugin/plugin.json` and updates README.md + CLAUDE.md in the SAME commit (release checklist).

---

### Task 1: `routing_for("hermes")` per-stage tier map

**Files:**
- Modify: `cli/cost.py` (the `routing_for` function, currently lines 88–107)
- Test: `tests/test_cost.py`

**Interfaces:**
- Produces: `routing_for("hermes") -> Dict[str, str]` mapping every `pipeline.STAGE_NAMES` entry to a tier alias. Planning/adversarial stages → `TIER_STRONG` ("opus"); execution stages → `TIER_MID` ("sonnet"). Task 3 consumes this.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cost.py`:

```python
def test_routing_for_hermes_routes_planning_strong_execution_mid():
    routes = routing_for("hermes")
    for stage in ("propose", "blueprint", "grill-blueprint", "spec", "grill-spec", "tasks"):
        assert routes[stage] == TIER_STRONG, stage
    for stage in ("research", "implement-task", "verify", "loop"):
        assert routes[stage] == TIER_MID, stage


def test_routing_for_hermes_covers_every_pipeline_stage():
    from cli.pipeline import STAGE_NAMES

    assert set(routing_for("hermes")) == set(STAGE_NAMES)
```

Check the existing imports at the top of `tests/test_cost.py` — ensure `TIER_MID`, `TIER_STRONG`, `routing_for` are imported from `cli.cost`; add them to the existing import line if missing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cost.py -q -k hermes`
Expected: 2 FAILED (`routing_for("hermes")` returns `{}` today).

- [ ] **Step 3: Implement** — in `cli/cost.py`, inside `routing_for`, insert before the final `return {}`:

```python
    if op == "hermes":
        # Per-STAGE tiers for the hermes conductor (keys = pipeline.STAGE_NAMES,
        # asserted in tests — update both together). Planning + adversarial
        # stages produce the reasoning artifacts everything downstream trusts →
        # strong; execution stages are mechanical against a finished spec → mid.
        return {
            "research": TIER_MID,
            "propose": TIER_STRONG,
            "blueprint": TIER_STRONG,
            "grill-blueprint": TIER_STRONG,
            "spec": TIER_STRONG,
            "grill-spec": TIER_STRONG,
            "tasks": TIER_STRONG,
            "implement-task": TIER_MID,
            "verify": TIER_MID,
            "loop": TIER_MID,
        }
```

Do NOT import `cli.pipeline` into `cli/cost.py` (keeps cost.py dependency-free/pure); the coverage lock lives in the test instead.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_cost.py -q`
Expected: all pass.

- [ ] **Step 5: Lint + commit**

```bash
python3 -m ruff check cli/ tests/
git add cli/cost.py tests/test_cost.py
git commit -m "feat: add per-stage hermes routing map to cost.routing_for"
```

---

### Task 2: stage-aware routed runner in `run_hermes`

**Files:**
- Modify: `cli/hermes.py` (typing import line 18, `run_hermes` signature lines 61–72, execute call line 118)
- Test: `tests/test_hermes.py`

**Interfaces:**
- Consumes: nothing new (routes dict passed in by caller).
- Produces: `run_hermes(..., stage_routes: Optional[Dict[str, str]] = None)`. Module-private `_stage_runner(make_runner, model)` helper. Task 3 wires the CLI to this param.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_hermes.py` (reuse that file's existing `AgentResult` import / fake-execute conventions):

```python
def test_stage_routes_model_reaches_runner_factory(tmp_path):
    models_seen = []

    def make_runner(model=None):
        models_seen.append(model)
        return None

    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    result = run_hermes(
        "start research", tmp_path,
        execute=execute, make_runner=make_runner,
        stage_routes={"research": "sonnet"},
    )
    assert result.ok
    # The intent-route call uses an unrouted runner (None); the stage-execute
    # runner is routed to the mapped tier.
    assert "sonnet" in models_seen


def test_stage_routes_tolerates_zero_arg_factory(tmp_path):
    # Existing callers/tests pass factories with no `model` kwarg — routing
    # must degrade to an unrouted runner, never crash.
    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    result = run_hermes(
        "start research", tmp_path,
        execute=execute, make_runner=lambda: None,
        stage_routes={"research": "sonnet"},
    )
    assert result.ok


def test_no_stage_routes_is_byte_identical_default(tmp_path):
    calls = []

    def make_runner(model=None):
        calls.append(model)
        return None

    def execute(stage, workspace, agent=None, prompt_prefix=""):
        return AgentResult(ok=True, output="done")

    run_hermes("start research", tmp_path, execute=execute, make_runner=make_runner)
    assert all(m is None for m in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_hermes.py -q -k "stage_routes or byte_identical"`
Expected: FAIL — `run_hermes() got an unexpected keyword argument 'stage_routes'`.

- [ ] **Step 3: Implement** — in `cli/hermes.py`:

3a. Extend the typing import: `from typing import Callable, Dict, List, Optional`.

3b. Add the helper below `_log`:

```python
def _stage_runner(make_runner: Callable, model: Optional[str]):
    """Build the stage-execution runner, routed to `model` when given.

    The model resolves AFTER the route has picked the stage — a runner made
    stage-blind can't be tier-routed. Falls back to a plain `make_runner()`
    for factories that don't accept a `model` kwarg (older callers, test
    stand-ins) — same tolerance pattern as `_invoke`.
    """
    if model is None:
        return make_runner()
    try:
        return make_runner(model=model)
    except TypeError:
        return make_runner()
```

3c. Add the param to `run_hermes` (after `gate: Optional[str] = None`):

```python
    stage_routes: Optional[Dict[str, str]] = None,
```

and document it in the docstring: `stage_routes` maps a stage name to a model alias (see `cost.routing_for("hermes")`); unmapped stages and `None` run unrouted. The intent-routing runner is deliberately NOT routed (classification is cheap).

3d. Replace the execute call (line 118):

```python
        runner = _stage_runner(make_runner, (stage_routes or {}).get(stage))
        run_result = _invoke(execute, stage, workspace, runner, prefix)
```

Leave line 104's `intent.route(message, workspace, make_runner())` untouched.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_hermes.py tests/test_intent.py -q`
Expected: all pass (existing hermes tests unaffected — param defaults to None).

- [ ] **Step 5: Lint + commit**

```bash
python3 -m ruff check cli/ tests/
git add cli/hermes.py tests/test_hermes.py
git commit -m "feat: stage-aware model routing in run_hermes (resolve model after route)"
```

---

### Task 3: wire `sigma hermes` CLI to stage routing (+ `--no-route`)

**Files:**
- Modify: `cli/main.py` (`cmd_hermes` lines 307–338, hermes parser lines 1003–1010)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1's `routing_for("hermes")`, Task 2's `stage_routes` param.
- Produces: `sigma hermes` routed by default; `--no-route` restores unrouted behavior.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_cli.py` (match that file's existing monkeypatch style for command tests):

```python
def test_cmd_hermes_routes_stages_by_default(monkeypatch, tmp_path):
    captured = {}

    def fake_run_hermes(message, ws, **kwargs):
        captured.update(kwargs)
        from cli.hermes import HermesResult
        return HermesResult(ok=True)

    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.hermes.run_hermes", fake_run_hermes)
    from cli.main import main
    assert main(["hermes", "continue", "--topic", "t"]) == 0
    routes = captured["stage_routes"]
    assert routes["spec"] == "opus"
    assert routes["implement-task"] == "sonnet"


def test_cmd_hermes_no_route_passes_empty_routes(monkeypatch, tmp_path):
    captured = {}

    def fake_run_hermes(message, ws, **kwargs):
        captured.update(kwargs)
        from cli.hermes import HermesResult
        return HermesResult(ok=True)

    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.hermes.run_hermes", fake_run_hermes)
    from cli.main import main
    assert main(["hermes", "continue", "--topic", "t", "--no-route"]) == 0
    assert captured["stage_routes"] == {}
```

NOTE for implementer: `cmd_hermes` imports `run_hermes` INSIDE the function body (`from cli.hermes import run_hermes`), so `monkeypatch.setattr("cli.hermes.run_hermes", ...)` is the correct patch point (patching `cli.main.run_hermes` would miss).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -q -k cmd_hermes`
Expected: FAIL with `KeyError: 'stage_routes'`.

- [ ] **Step 3: Implement** — in `cli/main.py`:

3a. In `cmd_hermes`, after the `sink = make_sink(...)` line, add:

```python
    from cli.cost import routing_for

    routes = {} if args.no_route else routing_for("hermes")
    if args.no_route:
        _print("  🧭 routing: off (--no-route) — CLI default model for every stage")
    else:
        _print("  🧭 routing: planning/grill stages→opus, execution stages→sonnet")
```

3b. In the `run_hermes(...)` call, change the runner factory and add the routes:

```python
            make_runner=lambda model=None: AgentRunner(model=model, trajectory_sink=sink),
            stage_routes=routes,
```

3c. In `build_parser`'s hermes section, add after the `--gate` argument:

```python
    ph.add_argument("--no-route", action="store_true",
                    help="disable per-stage model routing (default: planning/grill→strong, execution→mid)")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_cli.py tests/test_hermes.py -q`
Expected: all pass.

- [ ] **Step 5: Lint + commit**

```bash
python3 -m ruff check cli/ tests/
git add cli/main.py tests/test_cli.py
git commit -m "feat: route hermes stages by tier by default (--no-route opts out)"
```

---

### Task 4: `model_alias` passthrough in the claude adapter

**Files:**
- Modify: `cli/models.py` (`ModelAdapter` lines 43–65, `ADAPTERS["claude"]` lines 71–77, `run_model` lines 214–235)
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `ModelAdapter.model_args: List[str]` template field; `build_argv(..., model_alias: Optional[str] = None)`; `run_model(..., model_alias: Optional[str] = None)`. Task 5 consumes `run_model`'s new kwarg.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_models.py`:

```python
def test_build_argv_claude_injects_model_alias():
    argv = ADAPTERS["claude"].build_argv("hello", model_alias="opus")
    assert argv[:3] == ["claude", "--model", "opus"]
    assert argv[-2:] == ["-p", "hello"]


def test_build_argv_without_alias_is_unchanged():
    assert ADAPTERS["claude"].build_argv("hello") == ["claude", "-p", "hello"]


def test_build_argv_gpt_ignores_model_alias():
    # codex has no alias-passthrough --model contract (same law as
    # codex_argv_builder): the alias is dropped, argv unchanged.
    assert ADAPTERS["gpt"].build_argv("hi", model_alias="opus") == ADAPTERS["gpt"].build_argv("hi")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_models.py -q -k "alias"`
Expected: FAIL — `build_argv() got an unexpected keyword argument 'model_alias'`.

- [ ] **Step 3: Implement** — in `cli/models.py`:

3a. Add the field to `ModelAdapter` (after `deep_args`):

```python
    # Extra argv (template: {model}) injected right after the executable when a
    # model_alias is passed. Empty for adapters with no alias-passthrough
    # --model contract (gemini, codex) — the alias is then ignored, mirroring
    # codex_argv_builder's law.
    model_args: List[str] = field(default_factory=list)
```

3b. Extend `build_argv`:

```python
    def build_argv(
        self,
        prompt: str,
        deep: bool = False,
        sandbox: str = "read-only",
        model_alias: Optional[str] = None,
    ) -> List[str]:
        argv = [
            self.executable if a == "{exe}"
            else a.replace("{sandbox}", sandbox).replace("{prompt}", prompt)
            for a in self.arg_template
        ]
        if model_alias and self.model_args:
            argv[1:1] = [a.replace("{model}", model_alias) for a in self.model_args]
        if deep:
            argv.extend(self.deep_args)
        return argv
```

3c. Give the claude adapter the template: add `model_args=["--model", "{model}"],` to `ADAPTERS["claude"]`.

3d. Extend `run_model` — add `model_alias: Optional[str] = None` to the signature (after `deep`), and change the argv line to:

```python
    argv = adapter.build_argv(prompt, deep=deep, model_alias=model_alias)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_models.py tests/test_research.py tests/test_runner.py -q`
Expected: all pass (no existing caller passes the new kwarg).

- [ ] **Step 5: Lint + commit**

```bash
python3 -m ruff check cli/ tests/
git add cli/models.py tests/test_models.py
git commit -m "feat: model_alias passthrough on the claude adapter argv"
```

---

### Task 5: routed research synthesis (consume the dead routing key)

**Files:**
- Modify: `cli/research.py` (below `claude_synthesis_runner`, lines 97–113), `cli/main.py` (`cmd_research` lines 82–114, research parser lines 941–948)
- Test: `tests/test_research.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 4's `run_model(..., model_alias=...)`; existing `routing_for("research")["synthesis"]` (== "opus").
- Produces: `routed_synthesis_runner(model_alias: str) -> Callable[[str], str]` in `cli/research.py`; `sigma research` synthesizes on the strong tier by default, `--no-route` restores `claude_synthesis_runner`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_research.py`:

```python
def test_routed_synthesis_runner_passes_alias(monkeypatch):
    calls = {}

    def fake_run_model(model, prompt, model_alias=None, **kwargs):
        calls["model"] = model
        calls["alias"] = model_alias
        return ModelResult(model=model, ok=True, text="synth text")

    monkeypatch.setattr("cli.research.run_model", fake_run_model)
    runner = routed_synthesis_runner("opus")
    assert runner("some prompt") == "synth text"
    assert calls == {"model": "claude", "alias": "opus"}


def test_routed_synthesis_runner_degrades_to_empty_on_failure(monkeypatch):
    monkeypatch.setattr(
        "cli.research.run_model",
        lambda model, prompt, model_alias=None, **kw: ModelResult(model=model, ok=False, text="", error="boom"),
    )
    assert routed_synthesis_runner("opus")("p") == ""
```

(Import `routed_synthesis_runner` alongside the file's existing `cli.research` imports; `ModelResult` is already imported there.)

Append to `tests/test_cli.py`:

```python
def test_cmd_research_routes_synthesis_to_strong_tier(monkeypatch, tmp_path):
    captured = {}

    def fake_research(topic, models, ws, requested_tools=None, deep=False, web=False, synthesis_runner=None):
        captured["runner"] = synthesis_runner
        out = tmp_path / "research.md"
        out.write_text("x")
        return out

    calls = {}

    def fake_run_model(model, prompt, model_alias=None, **kwargs):
        calls["alias"] = model_alias
        from cli.models import ModelResult
        return ModelResult(model=model, ok=True, text="s")

    monkeypatch.setattr("cli.main.research", fake_research)
    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    monkeypatch.setattr("cli.research.run_model", fake_run_model)
    from cli.main import main
    assert main(["research", "some topic"]) == 0
    captured["runner"]("prompt")
    assert calls["alias"] == "opus"


def test_cmd_research_no_route_uses_default_synthesis(monkeypatch, tmp_path):
    captured = {}

    def fake_research(topic, models, ws, requested_tools=None, deep=False, web=False, synthesis_runner=None):
        captured["runner"] = synthesis_runner
        out = tmp_path / "research.md"
        out.write_text("x")
        return out

    monkeypatch.setattr("cli.main.research", fake_research)
    monkeypatch.setattr("cli.main.spec_workspace", lambda topic: tmp_path)
    from cli.main import main
    from cli.research import claude_synthesis_runner
    assert main(["research", "some topic", "--no-route"]) == 0
    assert captured["runner"] is claude_synthesis_runner
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_research.py tests/test_cli.py -q -k "routed_synthesis or routes_synthesis or no_route_uses_default"`
Expected: FAIL — `routed_synthesis_runner` doesn't exist; `cmd_research` has no `--no-route`.

- [ ] **Step 3: Implement**

3a. In `cli/research.py`, below `claude_synthesis_runner`, add:

```python
def routed_synthesis_runner(model_alias: str) -> Callable[[str], str]:
    """A `synthesis_runner` routed to a model tier (the cross-referencing pass
    is reasoning work — cost.routing_for("research") provisions TIER_STRONG).

    Same contract + degrade-to-"" failure behavior as `claude_synthesis_runner`,
    which stays as the unrouted (--no-route) path.
    """

    def run(prompt: str) -> str:
        result = run_model("claude", prompt, model_alias=model_alias)
        return result.text if result.ok else ""

    return run
```

Also update the stale `NOTE:` block in `claude_synthesis_runner`'s docstring — the routing key IS consumed now: routed by default via `routed_synthesis_runner` in `cmd_research`; this function is the `--no-route` fallback.

3b. In `cli/main.py`:
- Top import (line 33) becomes: `from cli.research import claude_synthesis_runner, research, routed_synthesis_runner`
- In `cmd_research`, before the `research(...)` call:

```python
    from cli.cost import routing_for

    if args.no_route:
        synthesis = claude_synthesis_runner
    else:
        synthesis_tier = routing_for("research")["synthesis"]
        synthesis = routed_synthesis_runner(synthesis_tier)
        _print(f"  🧭 routing: synthesis→{synthesis_tier}")
```

and pass `synthesis_runner=synthesis` instead of `synthesis_runner=claude_synthesis_runner`.

- In `build_parser`'s research section, add:

```python
    pr.add_argument("--no-route", action="store_true",
                    help="disable synthesis model routing (default: synthesis→strong tier)")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_research.py tests/test_cli.py -q`
Expected: all pass.

- [ ] **Step 5: Lint + commit**

```bash
python3 -m ruff check cli/ tests/
git add cli/research.py cli/main.py tests/test_research.py tests/test_cli.py
git commit -m "feat: route research synthesis to the strong tier by default"
```

---

### Task 6: docs + version bump (release checklist)

**Files:**
- Modify: `cli/__init__.py` (version), `.claude-plugin/plugin.json` (version), `README.md`, `CLAUDE.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Bump version**

`cli/__init__.py`: `__version__ = "0.24.0"`. `.claude-plugin/plugin.json`: `"version": "0.24.0"`.

- [ ] **Step 2: README.md**

In the `## ✨ Why sigma` autonomous bullet (the `hermes --auto` mention), add one sentence: `hermes --auto` now routes stages by tier — planning/grill stages on the strong model, execution stages on the mid tier (`--no-route` opts out) — and `sigma research`'s synthesis pass runs on the strong tier.

- [ ] **Step 3: CLAUDE.md**

- Commands section: add `--no-route` to the hermes + research entries.
- Gotchas: REPLACE the now-false gotcha *"That routing key exists but is deliberately UNCONSUMED — no `--route` flag on `sigma research` yet"* with: research synthesis is routed to `TIER_STRONG` by default via `routed_synthesis_runner`; `--no-route` restores the unrouted `claude_synthesis_runner`. Add a hermes gotcha: stage routing resolves AFTER `intent.route` picks the stage (`_stage_runner`); the intent-classification runner is deliberately unrouted; zero-arg `make_runner` factories degrade to unrouted (TypeError tolerance, same pattern as `_invoke`).
- While in the file, fix the two stale claims found on 2026-07-13: loop routing is ON by default (`--no-route` opts out; `--route` deprecated no-op), and `--team` has real git-worktree isolation (`cli/worktree.py`). Update the test count to the current collected number.

- [ ] **Step 4: Full suite + lint**

Run: `python3 -m pytest tests/ -q && python3 -m ruff check cli/ tests/`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add cli/__init__.py .claude-plugin/plugin.json README.md CLAUDE.md
git commit -m "chore: bump to 0.24.0, document hermes/research routing"
```
