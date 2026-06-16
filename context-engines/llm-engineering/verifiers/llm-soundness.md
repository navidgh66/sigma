---
domain: llm-engineering
description: PASS/WARN/FAIL verifier for prompt-injection defense, output schema validation, and cost guardrails.
---

# Verifier: LLM Soundness

## FAIL (block)
- **F1 injection unguarded**: untrusted input (user text, retrieved docs, tool output, web content)
  concatenated into the prompt with no delimiting/instruction-hierarchy defense, AND that content
  can trigger privileged actions (tool calls, data access). Treat all external text as hostile.
- **F2 no output validation**: structured output (JSON/enum/schema) consumed without parsing +
  validating; a malformed/extra-field response silently corrupts downstream logic.
- **F3 unbounded cost/loop**: LLM call inside a loop/agent with no `max_tokens`, no retry cap, no
  budget guard -> runaway spend.
- **F4 secrets/PII to model**: secrets, credentials, or unredacted PII placed in prompts/logs sent
  to a third-party API.
- **F5 unsanitized output to sink**: model output written to shell/SQL/HTML/eval without escaping
  (downstream injection: the model is an untrusted source too).

## WARN (justify or fix)
- **W1**: no `response_format`/tool-schema constraint where one exists for the provider.
- **W2**: no timeout/retry-with-backoff on API calls.
- **W3**: no prompt caching on a large stable prefix (cost left on the table).
- **W4**: no eval/golden-set gate on prompt or model changes.
- **W5**: no abstention path — model not instructed to say "I don't know" / "not in context".
- **W6**: per-request token/cost not logged -> no spend visibility or alerting.
- **W7**: model output trusted as ground truth without a confidence/verification step on critical paths.

## PASS
- External/untrusted content delimited and clearly marked as data; privileged actions gated
  (confirmation / allow-list), not driven directly by injected text.
- Outputs parsed against a schema; invalid responses rejected/retried, never silently used.
- `max_tokens`, timeout, retry cap, and a budget/cost guard on every call path.
- No secrets/PII in prompts or logs (redaction in place).
- Model output sanitized before any shell/SQL/HTML/eval sink.
- Eval gate on prompt/model changes; cost + latency logged.

## Quick checks
```python
import json, jsonschema
def safe_parse(text, schema):
    obj = json.loads(text)                 # F2: must validate, not trust
    jsonschema.validate(obj, schema)
    return obj
assert call_kwargs.get("max_tokens"), "F3: no token cap"
assert "{user_input}" not in privileged_system_prompt, "F1: raw user text in system prompt"
```

## Verdict format
```
LLM SOUNDNESS: FAIL
- F1: retrieved doc text inlined into system prompt; agent can call delete_account
- F2: response.json() used directly, no schema validation
- F3: no max_tokens on the summarizer loop
Delimit + de-privilege retrieved content; validate output; add max_tokens + budget guard.
```
