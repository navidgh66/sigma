# Codex cross-provider loop roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `sigma loop --execute` optionally run the verifier and (under `--tdd`) the test-writer role through the `codex` CLI instead of `claude`, giving a genuine cross-provider maker≠checker check, gated behind two new opt-in flags (`--codex-verify`, `--codex-tdd`).

**Architecture:** `AgentRunner` (`cli/runner.py`) gains two optional, additive fields — `argv_builder` (replaces its built-in `[claude, -p, ...]` argv construction when set) and `output_cleaner` (post-processes raw stdout, e.g. to strip codex's session-metadata preamble). `cli/models.py`'s existing `gpt` `ModelAdapter` (already `codex exec --sandbox read-only ...`) is parameterized to accept a `sandbox` value, and its `build_argv` is reused to build the codex `AgentRunner`'s argv via a small wrapper function. `cli/main.py`'s `cmd_loop` wires two new flags to swap the verifier/test-writer `AgentRunner` factories to codex-backed ones. No changes to `cli/loop.py`'s distinctness checks (identity-based, provider-agnostic already).

**Tech Stack:** Python 3.9, pytest, argparse, subprocess (via existing `AgentRunner.runner` injection pattern).

## Global Constraints

- Python 3.9 target — no `X | None` unions, use `Optional[X]` from `typing`.
- No new runtime dependencies (stdlib + existing pyyaml/rich only).
- Every existing test must stay green; all new optional fields default to `None` so untouched call sites are byte-identical (regression-locked by existing tests, per spec §1/§2).
- Prompt/argv passed via argv list, never shell string — no injection risk (existing convention, `test_adapter_argv_no_shell_injection` already enforces this for `cli/models.py`).
- `--codex-tdd` without `--tdd` is a usage error (spec §3).
- `--all` does NOT enable codex flags (spec "Rollout" — opt-in only, different risk class than in-box axes).
- Version bump (`cli/__init__.py` + `.claude-plugin/plugin.json`) + README.md + CLAUDE.md updates land in the same change as the code (repo release checklist, per CLAUDE.md "Conventions").
- ruff clean (`python3 -m ruff check cli/ tests/`) and full suite green (`python3 -m pytest tests/ -q`) before any commit that closes out a task.

---

## File Structure

- **Modify `cli/runner.py`** — add `argv_builder` + `output_cleaner` optional fields to `AgentRunner`; extract existing argv-building into `_default_argv`; apply `output_cleaner` to raw stdout before building `AgentResult`.
- **Modify `cli/models.py`** — parameterize the `gpt` adapter's `arg_template` with `{sandbox}`; add `sandbox` param to `ModelAdapter.build_argv` (default `"read-only"`, preserves current behavior); add a small `codex_argv_builder(sandbox)` factory function that returns an `argv_builder`-shaped callable sigma's loop can pass to `AgentRunner`.
- **Modify `cli/main.py`** — add `--codex-verify` / `--codex-tdd` argparse flags to the `loop` subcommand; validate `--codex-tdd` requires `--tdd`; branch `make_verifier`/`make_test_writer` factories to codex-backed runners when the flags are set; print status lines.
- **Modify `tests/test_runner.py`** — new tests for `argv_builder` and `output_cleaner`.
- **Modify `tests/test_models.py`** — new tests for `sandbox` param + `codex_argv_builder`.
- **Modify `tests/test_cli.py`** — new tests for the two new loop flags (usage error + factory wiring).
- **Modify `cli/__init__.py`** — version bump.
- **Modify `.claude-plugin/plugin.json`** — version bump.
- **Modify `README.md`** — document the two new flags.
- **Modify `CLAUDE.md`** — document the two new flags under Commands + a new Gotchas entry.

---

### Task 1: `AgentRunner` argv_builder + output_cleaner

**Files:**
- Modify: `cli/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces: `AgentRunner.argv_builder: Optional[Callable[[str, Optional[str]], List[str]]] = None` — when set, called as `argv_builder(prompt, self.model)` and its return value used as-is for the subprocess argv (bypasses `-p`/`--model` injection entirely).
- Produces: `AgentRunner.output_cleaner: Optional[Callable[[str], str]] = None` — when set, called on `proc.stdout` (raw, pre-strip) and its return value used as `AgentResult.output` (still `.strip()`-independent — the cleaner owns its own trimming; if `None`, current `.strip()` behavior is unchanged).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_runner.py` (after the existing `test_runner_model_injects_flag` test):

```python
def test_runner_argv_builder_bypasses_default_argv(monkeypatch):
    """A set argv_builder fully replaces the built-in [-p, --model] argv shape."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/codex")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    def builder(prompt, model):
        return ["codex", "exec", "--sandbox", "read-only", "--color", "never", prompt]

    AgentRunner(executable="codex", runner=spy, argv_builder=builder, model="ignored").run("hello")
    assert captured["argv"] == ["codex", "exec", "--sandbox", "read-only", "--color", "never", "hello"]


def test_runner_no_argv_builder_uses_default(monkeypatch):
    """argv_builder=None (default) is byte-identical to the pre-existing argv shape."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    captured = {}

    def spy(argv, *a, **k):
        captured["argv"] = argv
        return _fake_proc(0, "ok")

    AgentRunner(runner=spy).run("hello")
    assert captured["argv"] == ["claude", "-p", "hello"]


def test_runner_output_cleaner_applied(monkeypatch):
    """A set output_cleaner post-processes raw stdout before it becomes AgentResult.output."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/codex")
    raw = "workdir: /tmp\nVERDICT: PASS\n"
    runner = AgentRunner(
        executable="codex",
        runner=lambda *a, **k: _fake_proc(0, raw),
        output_cleaner=lambda text: "VERDICT: PASS",
    )
    res = runner.run("p")
    assert res.ok is True
    assert res.output == "VERDICT: PASS"


def test_runner_no_output_cleaner_strips_raw(monkeypatch):
    """output_cleaner=None (default) is byte-identical to today's bare .strip()."""
    import cli.runner as r

    monkeypatch.setattr(r.shutil, "which", lambda exe: "/bin/claude")
    runner = AgentRunner(runner=lambda *a, **k: _fake_proc(0, "  done  "))
    res = runner.run("p")
    assert res.output == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_runner.py -k "argv_builder or output_cleaner" -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'argv_builder'` (field doesn't exist yet).

- [ ] **Step 3: Implement**

In `cli/runner.py`, update the `AgentRunner` dataclass and `run` method:

```python
@dataclass
class AgentRunner:
    """Drives an agent CLI (default: claude). `runner` is injectable for tests.

    Two optional, independent extensions (both default to the prior behavior, so
    a bare `AgentRunner()` is byte-identical to before):

    - `model`: when set, `--model <alias>` is injected into the argv (e.g. "haiku"
      / "sonnet" / "opus"). The alias is passed straight through to the CLI — no
      model-ID map to drift. Powers the cost loop's intelligent model routing.
    - `trajectory_sink`: a `Callable[[dict], None]` called once per run with a
      step record (role, model, ok, verdict-free metadata, duration). Best-effort
      observability — a failing sink NEVER breaks the run (the inverse of a hard
      gate). `clock` supplies timestamps; `time.monotonic` by default.

    Two more optional fields extend this to non-claude-shaped CLIs (e.g. codex,
    whose argv is `exec --sandbox <mode> ...`, not `-p ...`), both additive:

    - `argv_builder`: `Callable[[str, Optional[str]], List[str]]`. When set, fully
      replaces the built-in `[-p, --model, prompt]` argv construction — called as
      `argv_builder(prompt, self.model)`, its return value used as-is.
    - `output_cleaner`: `Callable[[str], str]`. When set, applied to the raw
      (unstripped) stdout before it becomes `AgentResult.output` — e.g. to strip
      a CLI's session-metadata preamble (codex's `workdir:`/`tokens used:` lines)
      that would otherwise corrupt a verifier's `VERDICT:` parsing.
    """

    executable: str = "claude"
    timeout: int = 1800
    runner: Callable = subprocess.run
    model: Optional[str] = None
    trajectory_sink: Optional[Callable[[dict], None]] = None
    clock: Callable[[], float] = time.monotonic
    argv_builder: Optional[Callable[[str, Optional[str]], list]] = None
    output_cleaner: Optional[Callable[[str], str]] = None

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def _default_argv(self, prompt: str) -> list:
        argv = [self.executable, "-p"]
        if self.model:
            argv += ["--model", self.model]
        argv.append(prompt)
        return argv

    def run(self, prompt: str, cwd: Optional[Path] = None, role: str = "agent") -> AgentResult:
        """Run the agent non-interactively with the prompt; capture output.

        `role` labels the step for trajectory capture (implementer / verifier /
        logic / test-writer / stage name). It does not affect the argv.
        """
        if not self.available():
            result = AgentResult(ok=False, output="", error=f"{self.executable} CLI not found")
            self._emit(role, result, duration=0.0)
            return result

        argv = self.argv_builder(prompt, self.model) if self.argv_builder else self._default_argv(prompt)

        start = self.clock()
        try:
            proc = self.runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(cwd) if cwd else None,
            )
        except FileNotFoundError:
            result = AgentResult(ok=False, output="", error=f"{self.executable} not found at run time")
            self._emit(role, result, self.clock() - start)
            return result
        except subprocess.TimeoutExpired:
            result = AgentResult(ok=False, output="", error=f"timed out after {self.timeout}s")
            self._emit(role, result, self.clock() - start)
            return result

        duration = self.clock() - start
        raw_out = getattr(proc, "stdout", "") or ""
        out = self.output_cleaner(raw_out) if self.output_cleaner else raw_out.strip()
        if proc.returncode != 0:
            err = (getattr(proc, "stderr", "") or "").strip() or f"exit code {proc.returncode}"
            result = AgentResult(ok=False, output=out, error=err, returncode=proc.returncode)
        else:
            result = AgentResult(ok=True, output=out, returncode=0)
        self._emit(role, result, duration)
        return result
```

Only the two new fields, `_default_argv` extraction, the `argv = ...` line, and the `raw_out`/`out` lines change from the current file — everything else (imports, `AgentResult`, `_emit`, `write_artifact`) stays as-is.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_runner.py -v`
Expected: PASS — all existing + 4 new tests green.

- [ ] **Step 5: Commit**

```bash
git add cli/runner.py tests/test_runner.py
git commit -m "feat: add argv_builder + output_cleaner hooks to AgentRunner"
```

---

### Task 2: Parameterize codex adapter sandbox + add `codex_argv_builder`

**Files:**
- Modify: `cli/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing new from Task 1 (this task is independent — same underlying `codex exec` shape, just adds a `sandbox` param and a small builder function `cli/main.py` will import in Task 3).
- Produces: `ModelAdapter.build_argv(self, prompt: str, deep: bool = False, sandbox: str = "read-only") -> List[str]`.
- Produces: `codex_argv_builder(sandbox: str) -> Callable[[str, Optional[str]], List[str]]` — a factory whose returned callable matches `AgentRunner.argv_builder`'s signature `(prompt, model) -> List[str]` (ignores `model`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_models.py` (after `test_deep_args_appended_only_when_deep`):

```python
def test_gpt_adapter_sandbox_param_defaults_read_only():
    """Default sandbox is unchanged — byte-identical to pre-existing behavior."""
    adapter = ADAPTERS["gpt"]
    argv = adapter.build_argv("topic")
    assert "--sandbox" in argv and "read-only" in argv


def test_gpt_adapter_sandbox_param_overridable():
    adapter = ADAPTERS["gpt"]
    argv = adapter.build_argv("topic", sandbox="workspace-write")
    idx = argv.index("--sandbox")
    assert argv[idx + 1] == "workspace-write"
    assert "read-only" not in argv


def test_codex_argv_builder_read_only():
    from cli.models import codex_argv_builder

    build = codex_argv_builder("read-only")
    argv = build("do the thing", None)
    assert argv == ["codex", "exec", "--sandbox", "read-only", "--color", "never", "do the thing"]


def test_codex_argv_builder_workspace_write():
    from cli.models import codex_argv_builder

    build = codex_argv_builder("workspace-write")
    argv = build("write a test", "some-model-alias-ignored")
    assert argv == ["codex", "exec", "--sandbox", "workspace-write", "--color", "never", "write a test"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_models.py -k "sandbox or codex_argv_builder" -v`
Expected: FAIL — `TypeError: build_argv() got an unexpected keyword argument 'sandbox'` and `ImportError: cannot import name 'codex_argv_builder'`.

- [ ] **Step 3: Implement**

In `cli/models.py`, update the `gpt` adapter's `arg_template` to use a `{sandbox}` placeholder, update `ModelAdapter.build_argv` to substitute it, and add `codex_argv_builder`:

```python
    "gpt": ModelAdapter(
        name="gpt",
        executable="codex",
        # `codex exec` runs non-interactively, subscription-backed (ChatGPT login).
        # {sandbox} defaults to read-only via build_argv; the loop's codex-backed
        # test-writer role passes "workspace-write" instead (see codex_argv_builder).
        arg_template=["{exe}", "exec", "--sandbox", "{sandbox}", "--color", "never", "{prompt}"],
        # Enable Codex's built-in web_search tool for deep research.
        deep_args=["-c", "tools.web_search=true"],
    ),
```

Update `build_argv`:

```python
    def build_argv(self, prompt: str, deep: bool = False, sandbox: str = "read-only") -> List[str]:
        argv = [
            self.executable if a == "{exe}"
            else a.replace("{sandbox}", sandbox).replace("{prompt}", prompt)
            for a in self.arg_template
        ]
        if deep:
            argv.extend(self.deep_args)
        return argv
```

(Non-gpt adapters have no `{sandbox}` token in their `arg_template`, so `.replace("{sandbox}", sandbox)` is a no-op for them — behavior unchanged.)

Add near the bottom of the "argv builders" section, after the `ADAPTERS` dict and before `available_models`:

```python
def codex_argv_builder(sandbox: str) -> Callable[[str, Optional[str]], List[str]]:
    """Build an `AgentRunner.argv_builder`-shaped callable for a codex-backed role.

    `model` is accepted (to match AgentRunner's argv_builder signature) but
    ignored — codex's CLI has no alias-passthrough `--model` contract like
    claude's, so forcing a sigma model-tier alias through it would silently
    break if the alias isn't a real codex model name.
    """

    def build(prompt: str, model: Optional[str]) -> List[str]:
        return ADAPTERS["gpt"].build_argv(prompt, sandbox=sandbox)

    return build
```

Add `Callable` to the existing `from typing import Dict, List, Optional` import line → `from typing import Callable, Dict, List, Optional`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_models.py -v`
Expected: PASS — all existing + 4 new tests green.

- [ ] **Step 5: Commit**

```bash
git add cli/models.py tests/test_models.py
git commit -m "feat: parameterize codex adapter sandbox + add codex_argv_builder"
```

---

### Task 3: Wire `--codex-verify` / `--codex-tdd` into `sigma loop`

**Files:**
- Modify: `cli/main.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `cli.runner.AgentRunner(executable, argv_builder, output_cleaner, trajectory_sink)` (Task 1); `cli.models.codex_argv_builder(sandbox)` and `cli.models.clean_output(model, raw)` (Task 2, `clean_output` already exists and is exported from `cli/models.py`).
- Produces: two new argparse flags on the `loop` subcommand — `--codex-verify` (`store_true`, default `False`) and `--codex-tdd` (`store_true`, default `False`).

- [ ] **Step 1: Write the failing tests**

The parser-construction function is `build_parser()` (`cli/main.py:855`), already imported in `tests/test_cli.py` as `from cli.main import build_parser, cmd_init`. The one existing `cmd_loop`-level test, `test_cmd_loop_all_flag_applies_flip` (`tests/test_cli.py:402`), establishes the pattern for testing `cmd_loop` in-process: `chdir` into a `tmp_path` containing a `.git` dir (so `project_root()` resolves there), build the real workspace path via `date.today().isoformat()` + `slugify(topic)` (matching `spec_workspace`'s own logic — do not monkeypatch `spec_workspace` itself), write a `tasks.md` with one pending task, and monkeypatch `cli.main.run_loop` to a fake that records its kwargs (never invoke a real agent). Follow that exact pattern:

Add to `tests/test_cli.py` (near `test_cmd_loop_all_flag_applies_flip`):

```python
def test_codex_tdd_without_tdd_is_usage_error(tmp_path, monkeypatch, capsys):
    """--codex-tdd requires --tdd; without it, cmd_loop errors before running anything."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    def fake_run_loop(*a, **k):
        raise AssertionError("run_loop must not be called when --codex-tdd validation fails")

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--codex-tdd"])
    result = main_mod.cmd_loop(args)

    assert result == 1
    out = capsys.readouterr().out
    assert "--codex-tdd requires --tdd" in out


def test_codex_flags_default_false():
    args = build_parser().parse_args(["loop", "--topic", "t", "--execute"])
    assert args.codex_verify is False
    assert args.codex_tdd is False


def test_codex_verify_flag_parses():
    args = build_parser().parse_args(["loop", "--topic", "t", "--execute", "--codex-verify"])
    assert args.codex_verify is True


def test_codex_verify_wires_codex_backed_verifier(tmp_path, monkeypatch, capsys):
    """--codex-verify swaps make_verifier to a codex-backed factory; implementer untouched."""
    from datetime import date

    import cli.main as main_mod
    from cli.paths import slugify
    from cli.runner import AgentRunner

    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "sigma" / "specs" / f"{date.today().isoformat()}-{slugify('demo')}"
    ws.mkdir(parents=True)
    (ws / "tasks.md").write_text("- [ ] T1 (nlp): pending task\n")

    captured = {}

    def fake_run_loop(tasks, ws, skills_dir, max_cycles, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(main_mod, "run_loop", fake_run_loop)

    args = build_parser().parse_args(["loop", "--topic", "demo", "--execute", "--codex-verify"])
    main_mod.cmd_loop(args)

    verifier = captured["make_verifier"]()
    assert isinstance(verifier, AgentRunner)
    assert verifier.executable == "codex"
    assert verifier.argv_builder is not None

    implementer = captured["make_implementer"]()
    assert implementer.executable == "claude"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cli.py -k codex -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'codex_verify'` (or `'codex_tdd'`).

- [ ] **Step 3: Implement**

In `cli/main.py`, find the `loop` subparser block (`pl = ...` where the other `pl.add_argument(...)` calls live, right after the `--gate` argument at line ~919). Add:

```python
    pl.add_argument("--codex-verify", action="store_true",
                     help="run the verifier role via the codex CLI instead of claude "
                          "(genuine cross-provider maker≠checker)")
    pl.add_argument("--codex-tdd", action="store_true",
                     help="run the TDD test-writer role via the codex CLI instead of claude "
                          "(requires --tdd)")
```

In `cmd_loop`, right after the existing `if not args.execute:` plan-only block returns (i.e. as the first statement of the "Execute: real maker→checker cycles" section, before the `--all` handling at line ~161), add the validation:

```python
    if args.codex_tdd and not args.tdd:
        _print("✗ --codex-tdd requires --tdd (the test-writer role only exists in TDD mode)")
        return 1
```

Then, in the same section, after the existing imports (`from cli.cost import routing_for` etc.), add:

```python
    from cli.models import clean_output, codex_argv_builder
```

Add a helper next to the existing `_make` closure (defined right before `with keep_awake(...)`, around line 230):

```python
    def _make_codex(sandbox: str):
        return AgentRunner(
            executable="codex",
            argv_builder=codex_argv_builder(sandbox),
            output_cleaner=lambda raw: clean_output("gpt", raw),
            trajectory_sink=sink,
        )
```

Update the `run_loop(...)` call's `make_verifier` and `make_test_writer` kwargs (currently `make_verifier=lambda: _make(routes.get("verify"))` and `make_test_writer=(lambda: _make(routes.get("verify"))) if args.tdd else None`):

```python
        make_verifier=(lambda: _make_codex("read-only")) if args.codex_verify else (lambda: _make(routes.get("verify"))),
        make_test_writer=(
            (lambda: _make_codex("workspace-write")) if (args.tdd and args.codex_tdd)
            else ((lambda: _make(routes.get("verify"))) if args.tdd else None)
        ),
```

Add status-line prints alongside the existing `if args.tdd:`/`if args.team:` block (right after the `if args.advisor:` print block, before the `sink = make_sink(...)` line):

```python
    if args.codex_verify:
        _print("  🐙 codex-verify: verifier runs via codex (cross-provider maker≠checker)")
    if args.codex_tdd:
        _print("  🐙 codex-tdd: test-writer runs via codex")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: PASS — all existing + 3 new tests green.

Also run the full suite to confirm no regression from touching `cmd_loop`:

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass (779 + new ones).

- [ ] **Step 5: Commit**

```bash
git add cli/main.py tests/test_cli.py
git commit -m "feat: wire --codex-verify and --codex-tdd flags into sigma loop"
```

---

### Task 4: Docs + version bump

**Files:**
- Modify: `cli/__init__.py`
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing new — this task only documents Tasks 1-3's shipped behavior.
- Produces: nothing consumed by later tasks (this is the last task).

- [ ] **Step 1: Bump version**

Current version is `0.20.0` (tagged `v0.20.0`, `cli/__init__.py`). Repo convention is a minor bump per feature landing (e.g. `0.19.0` → `0.20.0` for the default-on loop axes). Bump to `0.21.0` in both files:

`cli/__init__.py`:
```python
__version__ = "0.21.0"
```

`.claude-plugin/plugin.json` — find the `"version"` key and update it to match:
```json
  "version": "0.21.0",
```

- [ ] **Step 2: Update README.md**

Find the `sigma loop` command documentation block (search for `--execute --all` or `--no-e2e` in README.md) and add the two new flags to the flag list, e.g.:

```
sigma loop --topic <t> --execute --codex-verify   # verifier runs via codex CLI (cross-provider maker≠checker)
sigma loop --topic <t> --execute --tdd --codex-tdd  # TDD test-writer runs via codex CLI (requires --tdd)
```

Place these lines directly after the existing `sigma loop --topic <t> --execute --tdd` line in README's command reference, matching its existing formatting/comment style exactly (inspect the surrounding lines before editing).

- [ ] **Step 3: Update CLAUDE.md**

Add the two flags to the `## Commands` code block in CLAUDE.md, directly after the existing `sigma loop --topic <t> --execute --tdd` line, matching the file's existing comment-alignment style:

```
sigma loop --topic <t> --execute --codex-verify   # verifier via codex CLI — cross-provider maker≠checker, opt-in
sigma loop --topic <t> --execute --tdd --codex-tdd  # test-writer via codex CLI, opt-in (requires --tdd)
```

Add a new bullet to the `## Gotchas` section (append at the end, following the file's existing gotcha-entry voice/format — each gotcha starts with the affected component and states the non-obvious behavior + the "why"):

```markdown
- `--codex-verify`/`--codex-tdd` (loop) run the verifier/test-writer role through
  the `codex` CLI instead of `claude` — a genuine cross-provider maker≠checker
  check (not just cross-prompt). Built on `AgentRunner`'s new `argv_builder`/
  `output_cleaner` hooks (`cli/runner.py`) — `argv_builder` replaces the
  claude-shaped `[-p, --model, prompt]` argv entirely (codex's shape is
  `exec --sandbox <mode> --color never <prompt>`, no `-p`); `output_cleaner`
  strips codex's session-metadata preamble (reuses `cli/models.py`'s
  `clean_output("gpt", ...)`) so `VERDICT:` parsing isn't corrupted by
  `workdir:`/`tokens used:` lines. Sandbox is role-specific: verifier is
  `read-only` (a checker must never mutate), test-writer is `workspace-write`
  (it writes a real failing-test file). `--codex-tdd` without `--tdd` is a
  usage error (the test-writer role doesn't exist outside TDD mode).
  Deliberately excluded from `--all` — codex needs a second CLI + its own
  `codex login` auth the user may not have set up (`cli/checks.py`'s
  `check_model_auth` already surfaces the login hint for research's gpt lane;
  same login covers this), so bundling it into `--all` would risk silently
  degrading every cycle to `codex CLI not found`. `--model` tier routing does
  NOT apply to codex-backed roles — codex has no alias-passthrough `--model`
  contract like claude's, so `codex_argv_builder` ignores the `model` arg it's
  passed (ModelAdapter reuse via `cli/models.py`'s `ADAPTERS["gpt"].build_argv`,
  not a separate codex adapter).
```

- [ ] **Step 4: Run full suite + lint**

Run: `python3 -m pytest tests/ -q`
Expected: all tests pass.

Run: `python3 -m ruff check cli/ tests/`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add cli/__init__.py .claude-plugin/plugin.json README.md CLAUDE.md
git commit -m "chore: bump version, document --codex-verify/--codex-tdd loop flags"
```

---

## Post-Plan: Merge + Release

Once all 4 tasks are committed and green, per the user's goal (approve spec → plan → implement → test → merge → deploy → release):

1. Working directly on `main` (confirmed at session start: branch is `main`, no feature branch) — commits already land on `main`, no PR/merge step needed.
2. Push to `origin main` (`git push`) — `--update`'s plugin-refresh path and any consumers of the CLI checkout pull from there.
3. Tag the release: repo convention is one annotated-or-lightweight tag per version bump (`v0.19.0`, `v0.20.0` both exist on prior bump commits). Tag the version-bump commit from Task 4 as `v0.21.0` and push the tag:

```bash
git tag v0.21.0
git push origin main --tags
```
