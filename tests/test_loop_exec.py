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
    """Returns a queued sequence of results, recording prompts it received."""

    def __init__(self, results):
        super().__init__()
        self._results = list(results)
        self.prompts = []

    def available(self):
        return True

    def run(self, prompt, cwd=None):
        self.prompts.append(prompt)
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


# --------------------------- contradiction flagging --------------------------- #
def test_ratchet_flags_contradiction(tmp_path):
    from cli.loop import ratchet_to_skills

    skills = tmp_path / "skills"
    # First lesson for nlp/tokenize-corpus.
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "lesson A", "nlp")
    # Second, same domain+topic → contradiction flagged.
    out2 = ratchet_to_skills(skills, "verify failed: tokenize corpus", "lesson B", "nlp")
    assert "⚠ CONTRADICTION" in out2.read_text()
    assert (skills / "CONTRADICTIONS.md").exists()


def test_ratchet_no_contradiction_different_topic(tmp_path):
    from cli.loop import ratchet_to_skills

    skills = tmp_path / "skills"
    ratchet_to_skills(skills, "verify failed: tokenize corpus", "A", "nlp")
    out2 = ratchet_to_skills(skills, "verify failed: train classifier", "B", "nlp")
    assert "⚠ CONTRADICTION" not in out2.read_text()
    assert not (skills / "CONTRADICTIONS.md").exists()


def test_execute_cycle_sets_contradiction(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    skills = tmp_path / "skills"
    # Pre-seed an existing lesson for the same task topic + domain (nlp/tokenize-corpus).
    from cli.loop import ratchet_to_skills

    ratchet_to_skills(skills, "verify failed: tokenize corpus", "old", "nlp")
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: FAIL")])
    out = execute_cycle(plan, tmp_path, skills, impl, chk)
    assert out.verified is False
    assert out.contradiction is not None


# --------------------------- recall injection --------------------------- #
RECALL = "--- past lessons (avoid repeating these mistakes) ---\n- use BPE\n--- end past lessons ---"


def test_recall_prepended_to_implement_and_verify_not_logic(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    logic = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])

    execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, logic, recall=RECALL)

    # Maker + checker see the recall block; the logic evaluator does not.
    assert RECALL in impl.prompts[0]
    assert RECALL in chk.prompts[0]
    assert RECALL not in logic.prompts[0]


def test_empty_recall_leaves_prompts_unchanged(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl_a = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk_a = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    execute_cycle(plan, tmp_path, tmp_path / "skills", impl_a, chk_a)  # default recall=""

    impl_b = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk_b = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    execute_cycle(plan, tmp_path, tmp_path / "skills", impl_b, chk_b, recall="")

    # Empty recall must be byte-identical to not passing recall at all.
    assert impl_a.prompts == impl_b.prompts
    assert chk_a.prompts == chk_b.prompts


def test_run_loop_injects_recall_from_prior_lessons(tmp_path):
    from cli.loop import ratchet_to_skills

    skills = tmp_path / "skills"
    # A prior nlp lesson exists → it must surface in the nlp task's prompts.
    ratchet_to_skills(skills, "verify failed: earlier nlp task", "use BPE not whitespace", "nlp")

    seen = {"impl": []}

    def mk_impl():
        r = ScriptedRunner([AgentResult(ok=True, output="i")])
        seen["impl"].append(r)
        return r

    run_loop(
        parse_tasks(TASKS), tmp_path, skills, max_cycles=10,
        make_implementer=mk_impl,
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
    )
    # The nlp implementer (first task) saw the recalled lesson.
    nlp_impl = seen["impl"][0]
    assert "use BPE not whitespace" in nlp_impl.prompts[0]


# --------------------------- gate in run_loop --------------------------- #
def _gate_script(tmp_path, wake: bool):
    """Write a tiny executable gate script that prints a wakeAgent decision."""
    p = tmp_path / "gate.sh"
    p.write_text(f'#!/bin/sh\necho \'{{"wakeAgent": {"true" if wake else "false"}}}\'\n')
    p.chmod(0o755)
    return str(p)


def test_run_loop_gate_skips(tmp_path):
    tasks = parse_tasks(TASKS)
    ran = []
    outcomes = run_loop(
        tasks, tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ran.append("i") or ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        gate=_gate_script(tmp_path, wake=False),
    )
    assert outcomes == []   # gate said skip → no cycles
    assert ran == []        # no agents constructed → zero tokens


def test_run_loop_gate_wakes(tmp_path):
    tasks = parse_tasks(TASKS)
    outcomes = run_loop(
        tasks, tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        gate=_gate_script(tmp_path, wake=True),
    )
    assert len(outcomes) == 2  # gate said wake → ran normally


# --------------------------- TDD mode (test-writer axis) --------------------------- #
def test_tdd_writes_test_before_implement(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    test = ScriptedRunner([AgentResult(ok=True, output="def test_x(): assert tokenize")])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, test_writer=test)
    assert out.test_written is True
    assert out.verified is True
    # The implementer's prompt embeds the failing test it must satisfy.
    assert "def test_x()" in impl.prompts[0]
    assert (tmp_path / "tests" / f"{plan.worktree_name}.md").exists()


def test_tdd_test_writing_failure_aborts_cycle(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    test = ScriptedRunner([AgentResult(ok=False, output="", error="no test")])
    impl = ScriptedRunner([AgentResult(ok=True, output="implemented")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    out = execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, test_writer=test)
    assert out.test_written is False
    assert out.implemented is False  # implementer never ran
    assert out.ratcheted_skill.exists()
    assert impl.prompts == []  # maker not invoked when no test exists


def test_tdd_test_writer_must_be_distinct(tmp_path):
    tasks = parse_tasks(TASKS)
    plan = plan_cycle(tasks[0])
    impl = ScriptedRunner([AgentResult(ok=True, output="i")])
    chk = ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")])
    with pytest.raises(ValueError):
        execute_cycle(plan, tmp_path, tmp_path / "skills", impl, chk, test_writer=impl)


def test_run_loop_tdd_mode(tmp_path):
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        make_test_writer=lambda: ScriptedRunner([AgentResult(ok=True, output="def test(): pass")]),
    )
    assert len(outcomes) == 2
    assert all(o.test_written for o in outcomes)


# --------------------------- team mode (parallel tasks) --------------------------- #
def test_run_loop_team_runs_all_tasks(tmp_path):
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
    )
    assert len(outcomes) == 2
    assert all(o.verified for o in outcomes)
    # Order preserved despite parallel execution.
    assert outcomes[0].task_title == "tokenize corpus"
    assert outcomes[1].task_title == "train agent"


def test_run_loop_team_respects_budget(tmp_path):
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=1,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        team=True,
    )
    assert len(outcomes) == 1


def test_run_loop_team_plus_tdd(tmp_path):
    outcomes = run_loop(
        parse_tasks(TASKS), tmp_path, tmp_path / "skills", max_cycles=10,
        make_implementer=lambda: ScriptedRunner([AgentResult(ok=True, output="i")]),
        make_verifier=lambda: ScriptedRunner([AgentResult(ok=True, output="VERDICT: PASS")]),
        make_test_writer=lambda: ScriptedRunner([AgentResult(ok=True, output="def t(): pass")]),
        team=True,
    )
    assert len(outcomes) == 2
    assert all(o.test_written and o.verified for o in outcomes)
