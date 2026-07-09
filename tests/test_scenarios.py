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
