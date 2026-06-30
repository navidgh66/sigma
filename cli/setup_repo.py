"""`sigma setup-repo` — one-shot per-repo bootstrap.

Globals (API keys, RTK, caveman, ccstatusline, graphify) are once-per-machine and
live in `sigma onboard`. THIS command is purely repo-local: it makes any repo
"sigma-ready" with its four important artifacts, in order:

  1. sigma.config.yml      — written if missing (self-contained; never clobbers one)
  2. .claude/settings.json — the SessionStart hook (idempotent)
  3. CLAUDE.local.md       — the learn-artifact pointer block (gitignored)
  4. ARCHITECTURE.md + .tours/*.tour — the codebase map (runs an agent; --no-learn skips,
     and it is skipped when the artifacts already exist)

All-yes by default (no per-step prompt); `--no-learn` opts out of the slow map step.
Every side effect is composed from existing pure/injectable modules, and the agent
driver (`learn_fn`) + filesystem writers are injected, so the whole flow is testable
without spawning an agent or touching global state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


@dataclass
class SetupRepoResult:
    config_written: bool = False
    hook_added: bool = False
    local_written: bool = False
    learned: bool = False
    learn_skipped_reason: Optional[str] = None
    steps: List[str] = field(default_factory=list)


def run_setup_repo(
    root: Path,
    domains: Optional[List[str]] = None,
    no_learn: bool = False,
    learn_fn: Optional[Callable] = None,
) -> SetupRepoResult:
    """Bootstrap `root` as a sigma repo. Returns what each step did.

    Idempotent: an existing config / configured hook / present map are left as-is.
    `learn_fn(root)` is injected in tests so the map step never spawns a real
    agent; in production it drives the real `sigma learn`.
    """
    from cli.claude_local import write_block
    from cli.config import SigmaConfig, config_path, write_config
    from cli.paths import DOMAINS
    from cli.session_context import build_pointer
    from cli.session_hook import install_session_hook, session_hook_status

    root = root.resolve()
    res = SetupRepoResult()

    # 1. Config — write only if missing (self-contained, never clobbers).
    if config_path(root).exists():
        res.steps.append("config: already present — kept")
    else:
        chosen = domains if domains else list(DOMAINS)
        write_config(SigmaConfig(name=root.name, domains=chosen), root=root)
        res.config_written = True
        res.steps.append(f"config: wrote sigma.config.yml ({', '.join(chosen)})")

    # 2. SessionStart hook — idempotent (skip when already configured).
    settings_path = root / ".claude" / "settings.json"
    if session_hook_status(settings_path=settings_path).get("configured"):
        res.steps.append("hook: already configured — kept")
    elif install_session_hook(settings_path=settings_path):
        res.hook_added = True
        res.steps.append("hook: added SessionStart → sigma session-context")
    else:
        res.steps.append("hook: could not write .claude/settings.json")

    # 3. CLAUDE.local.md pointer (gitignored). Reflects whatever artifacts exist now;
    #    the learn step below refreshes it again if it builds new ones.
    if write_block(root, build_pointer(root)):
        res.local_written = True
        res.steps.append("CLAUDE.local.md: wrote learn pointer (gitignored)")
    else:
        res.steps.append("CLAUDE.local.md: could not write")

    # 4. Map — the only slow/expensive step. Skipped on --no-learn or when artifacts
    #    already exist (don't re-spawn an agent over a prior map).
    _maybe_map(root, no_learn, learn_fn, res)
    return res


def _maybe_map(
    root: Path, no_learn: bool, learn_fn: Optional[Callable], res: SetupRepoResult
) -> None:
    from cli.learn import existing_artifacts

    if no_learn:
        res.learn_skipped_reason = "--no-learn"
        res.steps.append("map: skipped (--no-learn)")
        return
    if existing_artifacts(root):
        res.learn_skipped_reason = "artifacts already exist"
        res.steps.append("map: skipped (ARCHITECTURE.md / tour already present)")
        return

    learn_fn = learn_fn or _default_learn
    result = learn_fn(root)
    if getattr(result, "ok", False):
        res.learned = True
        res.steps.append("map: built ARCHITECTURE.md + CodeTour")
    else:
        err = getattr(result, "error", "unknown")
        res.learn_skipped_reason = f"learn failed: {err}"
        res.steps.append(f"map: learn did not finish ({err})")


def _default_learn(root: Path):
    """Drive the real `sigma learn` (run_learn refreshes CLAUDE.local.md itself)."""
    from cli.learn import run_learn

    return run_learn(root)
