from cli.loop import (
    append_loop_log,
    incomplete_tasks,
    parse_tasks,
    plan_cycle,
    ratchet_to_skills,
    render_skill,
    select_next,
)

TASKS_MD = """
# Tasks

- [ ] T1 (nlp): tokenize the corpus
- [x] T2 (mlops): register the model
- [ ] T3 (rl): train PPO agent
- not a task line
- [ ] plain task without id or domain
"""


def test_parse_tasks():
    tasks = parse_tasks(TASKS_MD)
    assert len(tasks) == 4
    assert tasks[0].id == "T1"
    assert tasks[0].domain == "nlp"
    assert tasks[0].done is False
    assert tasks[1].done is True


def test_incomplete_tasks():
    tasks = parse_tasks(TASKS_MD)
    pending = incomplete_tasks(tasks)
    assert len(pending) == 3
    assert all(not t.done for t in pending)


def test_plan_cycle_maker_checker():
    tasks = parse_tasks(TASKS_MD)
    plan = plan_cycle(tasks[0])
    assert plan.implementer_domain == "nlp"
    assert plan.valid_maker_checker() is True
    assert plan.worktree_name.startswith("sigma-loop-")


def test_plan_cycle_default_domain():
    tasks = parse_tasks(TASKS_MD)
    plain = [t for t in tasks if t.domain is None][0]
    plan = plan_cycle(plain)
    assert plan.implementer_domain == "ai-agent-engineering"


def test_select_next_respects_budget():
    tasks = parse_tasks(TASKS_MD)
    # already did max_cycles -> nothing more
    assert select_next(tasks, max_cycles=2, completed_count=2) is None
    # budget remaining -> returns first pending
    plan = select_next(tasks, max_cycles=10, completed_count=0)
    assert plan is not None
    assert plan.task.id == "T1"


def test_render_skill_has_frontmatter():
    body = render_skill("tokenizer mismatch", "Always align tokenizer to model", domain="nlp")
    assert body.startswith("---")
    assert "name: tokenizer-mismatch" in body
    assert "nlp" in body


def test_ratchet_writes_skill(tmp_path):
    out = ratchet_to_skills(tmp_path, "Off by one in returns", "Use t..T-1", domain="rl")
    assert out.exists()
    assert out.name == "SKILL.md"
    assert "off-by-one-in-returns" in str(out.parent)


def test_append_loop_log(tmp_path):
    log = append_loop_log(tmp_path, "cycle 1 done")
    log = append_loop_log(tmp_path, "cycle 2 done")
    text = log.read_text()
    assert "cycle 1 done" in text
    assert "cycle 2 done" in text
    assert text.count("- ") == 2


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
