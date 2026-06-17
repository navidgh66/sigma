import pytest

from cli.loop import (
    _verdict_pass,
    execute_cycle,
    parse_tasks,
    plan_cycle,
    run_loop,
)
from cli.runner import AgentResult, AgentRunner

TASKS = """
- [ ] T1 (nlp): tokenize corpus
- [ ] T2 (rl): train agent
"""


class ScriptedRunner(AgentRunner):
    """Returns a queued sequence of results."""

    def __init__(self, results):
        super().__init__()
        self._results = list(results)

    def available(self):
        return True

    def run(self, prompt, cwd=None):
        return self._results.pop(0)


def test_verdict_pass_parsing():
    assert _verdict_pass("stuff\nVERDICT: PASS") is True
    assert _verdict_pass("VERDICT: FAIL") is False
    assert _verdict_pass("no verdict here") is False  # skeptical default


def test_execute_cycle_pass(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk)
    assert out.implemented is True
    assert out.verified is True
    assert out.ratcheted_skill is None
    assert (tmp_path / "impl").exists()
    assert (tmp_path / "verify").exists()


def test_execute_cycle_verify_fail_ratchets(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: FAIL")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk)
    assert out.verified is False
    assert out.ratcheted_skill is not None
    assert out.ratcheted_skill.exists()


def test_execute_cycle_impl_fail_ratchets(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=False, output="", error="crash")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk)
    assert out.implemented is False
    assert out.verified is False
    assert out.ratcheted_skill.exists()


def test_execute_cycle_requires_distinct_agents(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    shared = ScriptedRunner([AgentResult(ok=True, output="x")])
    with pytest.raises(ValueError):
        execute_cycle(plan, tmp_path, tmp_path / "skills", shared, shared)


def test_run_loop_respects_budget(tmp_path):
    tasks = parse_tasks(TASKS)

    def mk_impl():
        return ScriptedRunner([AgentResult(ok=True, output="impl")])

    def mk_chk():
        return ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])

    outcomes = run_loop(tasks, tmp_path, tmp_path / "skills", max_cycles=1, make_implementer=mk_impl, make_verifier=mk_chk)
    assert len(outcomes) == 1  # capped at 1


def test_run_loop_all_tasks(tmp_path):
    tasks = parse_tasks(TASKS)
    outcomes = run_loop(
        tasks,
        tmp_path,
        tmp_path / "skills",
        max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
    )
    assert len(outcomes) == 2
    assert all(o.verified for o in outcomes)


# --------------------------- logic evaluator (second axis) --------------------------- #
def test_logic_checker_pass_both_axes(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    logic = ScriptedRunner([AgentResult(ok=True, output="reasoning sound\nVERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, logic)
    assert out.verified is True
    assert out.logic_ok is True
    assert (tmp_path / "verify" / f"{plan.worktree_name}.logic.md").exists()


def test_logic_fail_fails_cycle_even_if_quality_passes(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    logic = ScriptedRunner([AgentResult(ok=True, output="wrong approach\nVERDICT: FAIL")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, logic)
    assert out.verified is False
    assert out.logic_ok is False
    assert out.ratcheted_skill.exists()


def test_logic_checker_must_be_distinct(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    with pytest.raises(ValueError):
        execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, chk)


def test_run_loop_with_logic_checker(tmp_path):
    tasks = parse_tasks(TASKS)
    outcomes = run_loop(
        tasks,
        tmp_path,
        tmp_path / "skills",
        max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        make_logic_checker=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
    )
    assert len(outcomes) == 2
    assert all(o.verified and o.logic_ok for o in outcomes)
