---
domain: ai-agent-engineering
description: PASS/WARN/FAIL verifier for tool schema validity, eval coverage, and maker/checker separation.
---

# Verifier: Agent Soundness

## FAIL (block)
- **F1 invalid tool schema**: tool `input_schema` is malformed, missing `required`, or types don't
  match what the implementation reads/validates. Schema and handler must agree.
- **F2 no server-side validation**: tool trusts model-supplied args directly (path/SQL/shell built
  from raw input) — injection / unsafe execution risk.
- **F3 maker == checker**: the agent that performs a destructive/irreversible action also self-approves
  it; no independent confirmation or evaluator. (Refunds, deletes, sends, deploys.)
- **F4 unbounded loop/cost**: agent loop has no step cap, budget guard, or stuck-loop detection.
- **F5 no eval suite**: changes to agent behavior with no automated eval to catch regressions.
- **F6 prompt-injection unguarded**: tool outputs / retrieved content flow into the model with no
  defense, and no eval case tests injection resistance.

## WARN (justify or fix)
- **W1**: overlapping/ambiguous tools likely to be mis-selected.
- **W2**: eval suite too small (<20 cases) or only happy-path (no error/adversarial/multi-step).
- **W3**: evals judge text plausibility instead of end-state/ground-truth.
- **W4**: unbounded tool outputs piped into context (no truncation) -> window overflow risk.
- **W5**: errors returned as raw tracebacks/HTTP codes (no recovery hint).
- **W6**: LLM-as-judge used without validation against human labels.
- **W7**: no per-tag eval breakdown -> regressions hard to localize.

## PASS
- Every tool schema valid, typed, with bounds/enums; matches its handler; args validated server-side.
- Destructive actions gated by independent confirmation/evaluator (maker/checker separated).
- Loop has step cap + budget guard + stuck detection.
- Eval suite covers happy/edge/error/multi-step/adversarial, tagged, isolated, with end-state checks.
- Prompt-injection defense present and tested by eval cases.
- Tool outputs truncated; errors actionable.

## Quick checks
```python
import jsonschema
for t in tools:
    jsonschema.Draft7Validator.check_schema(t["input_schema"])   # F1
assert any("adversarial" in c.tags for c in suite), "F6/W2: no injection eval"  # F6
assert agent.max_steps and agent.budget, "F4: no loop bound"     # F4
```

## Verdict format
```
AGENT SOUNDNESS: FAIL
- F3: refund_agent issues and confirms its own refunds, no checker
- F4: agent loop has no max_steps
- W2: 8 eval cases, all happy-path
Add an approval step for refunds; cap the loop; expand evals with error/adversarial cases.
```
