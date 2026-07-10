# Codex cross-provider loop roles — design

**Date:** 2026-07-10
**Status:** approved, pending implementation plan

## Context

sigma's `AgentRunner` (`cli/runner.py`) is the single execution chokepoint for
`sigma loop` / `sigma hermes`. It hardcodes `executable="claude"` and builds
argv as `[claude, -p, <optional --model tier>, prompt]`. Model-tier routing
(`cli/cost.py`'s `routing_for("loop")`) already sends mechanical roles
(implement/verify/test-writer/simplifier) to `sonnet` and reasoning roles
(logic/advisor/e2e) to `opus` — that tiering was checked and confirmed
correct against the user's stated principle (opus reserved for
planning/logic-heavy judgment, sonnet for worker/coding roles). No change
needed there.

Separately, `sigma research` already drives three provider CLIs in parallel
(`cli/models.py`'s `ADAPTERS`: claude, gemini, gpt via `codex exec`). That
adapter proves codex is subscription-backed (ChatGPT login, no API key) and
scriptable via subprocess with a distinct argv shape:
`codex exec --sandbox <mode> --color never <prompt>` (no `-p` flag, unlike
claude/gemini).

The user has an official `openai-codex` Claude Code plugin installed
(cached at `~/.claude/plugins/cache/openai-codex/codex/1.0.1`), but its
`/codex:review` etc. commands are **session-scoped**: they shell out via
`node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" ...` and require a
live Claude Code session (`CLAUDE_PLUGIN_ROOT` env, session lifecycle hooks).
`sigma loop`/`hermes` run headless as a subprocess CLI with no session — the
plugin's commands are not callable from there. This design integrates codex
the same way `cli/models.py` already does: a direct `codex exec` subprocess,
not the plugin.

## Goal

Let `sigma loop --execute` optionally run two roles through codex instead of
claude, so the loop gets a genuine cross-provider check instead of two
same-provider agents disagreeing only by prompt:

1. **Codex as verifier/checker** — codex reviews claude's implementation.
   Maker (claude) ≠ checker (codex) is now also maker≠checker **across
   providers**, not just across prompts.
2. **Codex as TDD test-writer** — codex pens the failing test (RED) before
   claude implements to pass it, when `--tdd` is on. A different model
   writing the test can catch coverage gaps a same-model pair might share.

Both are opt-in flags. Default behavior (no flags) is byte-identical to
today — claude for every role.

## Non-goals

- Not touching the model-tier routing logic (already correct).
- Not wiring codex into logic-evaluator, advisor, or e2e roles — those need
  the deepest reasoning tier and adversarial-review framing isn't the ask
  here; can be added later following the same pattern if wanted.
- Not integrating the `openai-codex` plugin's `codex-companion.mjs` runtime,
  session hooks, or job queue — headless loop has no session to hook into.
- Not adding a `--codex-*` flag for every role; only verifier and test-writer,
  matching the two roles the user picked.

## Design

### 1. `AgentRunner` gains an injectable argv builder

`cli/runner.py`'s `AgentRunner` currently builds argv inline:
`[executable, "-p", *(--model tier), prompt]`. This shape is claude/gemini-
specific (`-p` flag) and wrong for codex (`exec --sandbox <mode> ...`, no
`-p`).

Add one new optional field:

```python
@dataclass
class AgentRunner:
    executable: str = "claude"
    timeout: int = 1800
    runner: Callable = subprocess.run
    model: Optional[str] = None
    trajectory_sink: Optional[Callable[[dict], None]] = None
    clock: Callable[[], float] = time.monotonic
    argv_builder: Optional[Callable[[str, Optional[str]], List[str]]] = None
```

`argv_builder(prompt, model) -> List[str]` fully replaces the built-in argv
construction when set. `None` (default) preserves today's exact behavior —
existing callers (loop's claude/gemini roles, review, profile, eval) are
byte-identical; this is purely additive, like every other optional
`AgentRunner` field (`model`, `trajectory_sink`).

`AgentRunner.run` becomes:

```python
argv = self.argv_builder(prompt, self.model) if self.argv_builder else self._default_argv(prompt)
```

where `_default_argv` is the existing `[executable, -p, ...]` logic extracted
unchanged.

### 2. A codex argv builder, shared with `cli/models.py`

`cli/models.py`'s `gpt` adapter already has the right argv shape but bakes in
a fixed `--sandbox read-only`. Parameterize it:

```python
arg_template=["{exe}", "exec", "--sandbox", "{sandbox}", "--color", "never", "{prompt}"]
```

`ModelAdapter.build_argv` gains a `sandbox: str = "read-only"` param,
substituting `{sandbox}` (default preserves the current research behavior
byte-for-byte — regression-locked by existing tests).

Add a small builder function in `cli/runner.py` (or a new tiny
`cli/codex_runner.py` if it doesn't fit `runner.py`'s pure-dataclass shape —
decide during planning) that wraps this into the `argv_builder` signature:

```python
def codex_argv_builder(sandbox: str) -> Callable[[str, Optional[str]], List[str]]:
    def build(prompt: str, model: Optional[str]) -> List[str]:
        return ["codex", "exec", "--sandbox", sandbox, "--color", "never", prompt]
    return build
```

`model` is accepted but ignored — codex's CLI has no `--model` alias-passthrough
contract like claude's; forcing a tier through `--model` would silently break
if the alias isn't a real codex model name. (`--model` support can be added
later if needed; out of scope here.)

Codex's raw stdout needs the same event/preamble stripping `cli/models.py`'s
`_clean_codex` already does for research. `AgentRunner.run` currently does
`(proc.stdout or "").strip()` with no per-provider cleaning. Add a matching
`output_cleaner: Optional[Callable[[str], str]] = None` field (same
additive-default-None pattern) so the codex-backed runner can pass
`clean_output` (imported from `cli/models.py`) or a thin wrapper. Without
this, codex's session-metadata lines (`workdir:`, `tokens used:`, etc.) would
leak into the verifier's/test-writer's `VERDICT:` parsing and corrupt the
skeptical-default-FAIL logic in `_verdict_pass`.

### 3. Two new CLI flags on `sigma loop`

```
--codex-verify     verifier role runs via codex (cross-provider maker≠checker)
--codex-tdd         test-writer role runs via codex (requires --tdd; error if --tdd is off)
```

In `cmd_loop` (`cli/main.py`), where `_make(role_tier)` currently builds every
`AgentRunner`, branch per-role:

```python
def _make_codex(sandbox: str):
    return AgentRunner(
        executable="codex",
        argv_builder=codex_argv_builder(sandbox),
        output_cleaner=lambda raw: clean_output("gpt", raw),
        trajectory_sink=sink,
    )

make_verifier = (lambda: _make_codex("read-only")) if args.codex_verify else (lambda: _make(routes.get("verify")))
make_test_writer = (
    (lambda: _make_codex("workspace-write")) if (args.tdd and args.codex_tdd)
    else ((lambda: _make(routes.get("verify"))) if args.tdd else None)
)
```

Sandbox choice: verifier is read-only (a checker should never mutate);
test-writer needs `workspace-write` (it writes a real test file to disk).

Validation: `--codex-tdd` without `--tdd` is a usage error (`args.error(...)`
via argparse, matching existing flag-dependency checks in `cmd_loop` if any
exist, else a plain `_print` + return 1 at the top of `cmd_loop`).

Print lines, matching the existing `_print(f"  🧭 routing: ...")` convention:

```
  🐙 codex-verify: verifier runs via codex (cross-provider maker≠checker)
  🐙 codex-tdd: test-writer runs via codex
```

### 4. Distinctness is unaffected

`execute_cycle`'s `is`-identity checks (`ValueError` on maker==checker etc.)
operate on object identity, not provider. A codex-backed `AgentRunner` is
still a distinct Python object from the claude-backed implementer — no
change needed to `cli/loop.py`.

### 5. Preflight: codex CLI availability

`AgentRunner.available()` already does `shutil.which(self.executable)`. With
`executable="codex"` set, this correctly detects a missing `codex` binary and
degrades to the existing `AgentResult(ok=False, error="codex CLI not found")`
path — same fail-safe shape as a missing claude/gemini, no new code needed.
`cli/checks.py`'s `check_models`/`check_model_auth` already probe for `codex`
(used by research's gpt lane) — `sigma doctor` already surfaces a missing/
unauthenticated codex CLI; no new check needed.

## Testing

- `cli/runner.py`: new test — `argv_builder` set → argv matches builder
  output exactly, bypasses `-p`/`--model` injection; `argv_builder=None` →
  byte-identical to current tests (regression lock).
- `cli/runner.py`: `output_cleaner` set → cleaned text used for
  `AgentResult.output`; unset → raw `.strip()` (regression lock).
- `cli/models.py`: `build_argv(..., sandbox="workspace-write")` produces the
  parameterized argv; default `sandbox="read-only"` byte-identical to
  existing test (regression lock on research's gpt lane).
- `cli/main.py` / `test_cli.py`: `--codex-tdd` without `--tdd` → usage error,
  no cycle runs. `--codex-verify` alone → verifier AgentRunner has
  `executable="codex"`; implementer untouched (still claude/routed sonnet).
- `cli/loop.py`: no changes expected; existing maker≠checker tests must stay
  green untouched (proves distinctness logic is provider-agnostic already).

## Rollout

Opt-in only (`--codex-verify`, `--codex-tdd`), so no default-behavior change
and no README "default flags" confusion repeat (the `--all`/default-on axes
work from 2026-07-09 stays as-is; codex flags are NOT added to `--all` —
they require a second CLI + auth the user may not have set up, so
`--all` opting into an unavailable provider would silently degrade every
cycle to a `codex CLI not found` fail. `--all` continues to mean "every
axis this repo already supports out of the box"; codex flags are power-user
opt-in like `--tdd`/`--team` were before their consumers existed).

Version bump (`cli/__init__.py` + `.claude-plugin/plugin.json`) +
README.md + CLAUDE.md updates land in the same change as the code, per the
repo's release checklist.
