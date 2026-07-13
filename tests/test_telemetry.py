import json

from cli.telemetry import UsageEnvelope, parse_result_envelope


def _envelope(**overrides):
    data = {
        "type": "result",
        "subtype": "success",
        "result": "VERDICT: PASS",
        "total_cost_usd": 0.0123,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 700,
            "cache_creation_input_tokens": 30,
        },
    }
    data.update(overrides)
    return json.dumps(data)


def test_parse_valid_envelope_extracts_text_and_usage():
    env = parse_result_envelope(_envelope())
    assert env is not None
    assert env.text == "VERDICT: PASS"
    assert env.input_tokens == 100
    assert env.output_tokens == 50
    assert env.cache_read_tokens == 700
    assert env.cache_creation_tokens == 30
    assert env.cost_usd == 0.0123
    assert env.total_tokens == 880


def test_parse_envelope_missing_usage_defaults_to_zero():
    env = parse_result_envelope(json.dumps({"result": "text only"}))
    assert env is not None
    assert env.text == "text only"
    assert env.total_tokens == 0
    assert env.cost_usd is None


def test_parse_non_json_returns_none():
    assert parse_result_envelope("plain agent prose, not an envelope") is None
    assert parse_result_envelope("") is None
    assert parse_result_envelope("   ") is None


def test_parse_json_non_dict_returns_none():
    assert parse_result_envelope("[1, 2, 3]") is None
    assert parse_result_envelope('"just a string"') is None


def test_parse_envelope_without_result_text_returns_none():
    # A usage blob with no result text is not a usable envelope — degrading to
    # the raw-text path beats emitting empty output with confident numbers.
    assert parse_result_envelope(json.dumps({"usage": {"input_tokens": 5}})) is None
    assert parse_result_envelope(json.dumps({"result": 42})) is None


def test_parse_envelope_garbage_usage_values_coerce_to_zero():
    env = parse_result_envelope(
        json.dumps({"result": "ok", "usage": {"input_tokens": "many", "output_tokens": True},
                    "total_cost_usd": "free"})
    )
    assert env == UsageEnvelope(text="ok")
