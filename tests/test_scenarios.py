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


def test_render_eval_set_round_trips_through_eval_parser():
    from cli.eval import parse_eval_set
    from cli.scenarios import Scenario, render_eval_set

    scenarios = [
        Scenario(name="Happy Path!", given="a fresh db", when="the flow runs", then="a row exists"),
        Scenario(name="null input rejected", given="an empty payload", when="submitted", then="a 400 is returned"),
    ]
    text = render_eval_set("demo-topic", scenarios)
    cases = parse_eval_set(text)
    assert [c.id for c in cases] == ["happy-path", "null-input-rejected"]
    assert "Given a fresh db" in cases[0].input
    assert "Then a row exists" in cases[0].rubric
    assert cases[1].rubric.endswith("Then a 400 is returned")


def test_render_eval_set_deterministic():
    from cli.scenarios import Scenario, render_eval_set

    sc = [Scenario(name="x", given="g", when="w", then="t")]
    assert render_eval_set("t", sc) == render_eval_set("t", sc)
