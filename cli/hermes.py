"""Hermes — the optional conductor that drives sigma from plain language.

Hermes is purely additive: standalone `sigma <stage>` commands are untouched.
Given a message, Hermes routes to the next stage (state-driven by default,
intent-classified on override), injects the stage's bundled skill, runs the
stage through the agent runner, and appends an event for the board. In single-
step mode it runs one hop and stops; in `--auto` it chains stages until a human
gate (spec approval, verify failure), a stage failure, or the hop budget.

The stage executor and runner factory are injected, so the whole conductor is
testable without spawning real agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli import events, intent, skill_map
from cli.loop import _verdict_pass
from cli.pipeline import execute_stage as _real_execute_stage
from cli.runner import AgentResult

# Stages that require a human to approve/inspect before Hermes continues in auto.
SPEC_GATE_STAGE = "spec"
VERIFY_STAGE = "verify"
DEFAULT_MAX_HOPS = 12


@dataclass
class HermesResult:
    ok: bool
    stages_run: List[str] = field(default_factory=list)
    auto: bool = False
    gate: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def _log(workspace: Path, message: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    log = workspace / "hermes-log.md"
    if not log.exists():
        log.write_text("# Hermes log\n\n")
    with log.open("a") as fh:
        fh.write(f"- {message}\n")


def run_hermes(
    message: str,
    workspace: Path,
    auto: bool = False,
    terse: bool = False,
    max_hops: int = DEFAULT_MAX_HOPS,
    execute: Optional[Callable] = None,
    make_runner: Optional[Callable] = None,
    vendor: Optional[Path] = None,
    now: Optional[str] = None,
    gate: Optional[str] = None,
) -> HermesResult:
    """Route + run one stage (default) or chain until a gate (auto).

    `execute(stage_name, workspace, agent=None)` runs a stage and returns an
    AgentResult. `make_runner()` yields a fresh runner for routing/execution.
    Both are injectable for tests.

    `gate`, when set, is a wakeAgent script checked before each hop; a skip
    decision stops the run before spending tokens on that hop.
    """
    execute = execute or _real_execute_stage
    make_runner = make_runner or (lambda: None)
    vendor = vendor or skill_map.vendor_dir()

    result = HermesResult(ok=True, auto=auto)
    hops = 0

    while True:
        if hops >= max_hops:
            result.gate = "budget-cap"
            _log(workspace, f"stopped: budget cap ({max_hops} hops)")
            break

        if gate:
            from cli.gate import run_gate

            decision = run_gate(gate, cwd=workspace)
            if not decision.wake:
                result.gate = "wake-gate"
                _log(workspace, f"stopped: {decision.reason}")
                break

        route = intent.route(message, workspace, make_runner())
        stage = route.stage
        if stage is None:
            result.gate = "no-route"
            _log(workspace, "stopped: no route resolved")
            break

        # Inject the stage's bundled skill into the prompt prefix.
        prefix = skill_map.inject_skill("", stage, vendor, terse=terse)

        events.append_event(
            workspace,
            events.Event(task=stage, stage=stage, status=events.STATUS_IN_PROGRESS, ts=now),
        )
        run_result = _invoke(execute, stage, workspace, make_runner(), prefix)
        hops += 1
        result.stages_run.append(stage)

        if not run_result.ok:
            events.append_event(
                workspace,
                events.Event(task=stage, stage=stage, status=events.STATUS_FAILED, ts=now),
            )
            _log(workspace, f"{stage}: FAILED ({run_result.error})")
            result.ok = False
            result.gate = "stage-failed"
            break

        # Verify stage: stop the chain on a FAIL verdict (human gate).
        if stage == VERIFY_STAGE and not _verdict_pass(run_result.output or ""):
            events.append_event(
                workspace,
                events.Event(
                    task=stage, stage=stage, status=events.STATUS_FAILED,
                    verdict="FAIL", ts=now,
                ),
            )
            _log(workspace, f"{stage}: verify FAILED — stopping for review")
            result.gate = "verify-failed"
            break

        events.append_event(
            workspace,
            events.Event(task=stage, stage=stage, status=events.STATUS_DONE, ts=now),
        )
        _log(workspace, f"{stage}: done")

        if not auto:
            break

        # Auto mode: stop at the spec-approval gate so a human can review.
        if stage == SPEC_GATE_STAGE:
            result.gate = "spec-approval"
            _log(workspace, "reached spec-approval gate — awaiting human review")
            break

        # Continue the chain from the (now advanced) workspace state.
        message = "continue"

    return result


def _invoke(execute: Callable, stage: str, workspace: Path, runner, prefix: str) -> AgentResult:
    """Call the stage executor, passing skill prefix/agent only if it accepts them."""
    try:
        return execute(stage, workspace, agent=runner, prompt_prefix=prefix)
    except TypeError:
        # Test stand-ins use a simpler signature.
        return execute(stage, workspace, agent=runner)
