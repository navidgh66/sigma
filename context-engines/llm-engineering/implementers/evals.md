---
domain: llm-engineering
description: LLM output evals — golden sets, LLM-as-judge, and regression gating in CI.
---

# LLM Evals

## Eval-first, always
Prompt/model/RAG changes look fine in the demo and break in three other cases. Build a golden set
and run it on every change. "It seems better" is not a signal; a pass-rate delta is.

## Golden set
```python
@dataclass
class Case:
    id: str
    input: dict
    expected: str | None        # exact/regex for deterministic tasks
    rubric: str | None          # for judged quality
    tags: list[str]
```
- 50-200 cases covering real usage + known failures + edge/adversarial inputs.
- Tag by capability so you can localize regressions.
- Version it; freeze it; grow it whenever a prod bug appears (turn bugs into cases).

## Scoring tiers (prefer cheap + deterministic first)
1. **Exact / regex / schema**: classification, extraction, JSON validity. Free, reliable.
2. **Programmatic**: does the code run, does the SQL parse, is the number within tolerance.
3. **Embedding similarity**: semantic closeness to a reference (noisy; a screen, not a verdict).
4. **LLM-as-judge**: open-ended quality (helpfulness, faithfulness, tone) — last resort, validated.

## LLM-as-judge (done right)
```python
judge_prompt = """Score the RESPONSE against the rubric, 0-3.
Rubric: {rubric}
QUESTION: {q}\nRESPONSE: {a}
Return JSON: {{"score": <0-3>, "reason": "<short>"}}"""
```
- Use a **strong** model as judge, ideally different family than the one under test.
- **Pairwise** comparison (A vs B) is more reliable than absolute scoring; randomize order to kill
  position bias.
- Provide an explicit ordinal rubric, not "rate 1-10".
- **Validate the judge against human labels** on a sample — measure judge-human agreement before trusting it.
- Beware self-preference bias (models favor their own style).

## Regression gating
```python
results = run_suite(suite)
pass_rate = mean(r.passed for r in results)
assert pass_rate >= BASELINE - TOLERANCE, f"Regression: {pass_rate:.2f} < baseline"
# Block the PR/deploy on regression; report per-tag deltas.
```
Run in CI on prompt/model/RAG changes. Track cost + latency per case alongside quality.

## Pitfalls
- No golden set -> flying blind; every change is a gamble.
- LLM-judge unvalidated -> trusting a noisy/biased grader.
- Absolute 1-10 scoring -> high variance, uncalibrated.
- Position bias in pairwise judging (always picks A) -> randomize.
- Only happy-path cases -> misses the failures that matter.
- Judge == model under test -> self-preference inflation.

## Checklist
- [ ] Versioned golden set, tagged, covering edge/adversarial cases
- [ ] Deterministic scoring used wherever possible
- [ ] LLM-judge validated vs human labels; pairwise + order-randomized
- [ ] CI regression gate vs baseline with per-tag deltas
- [ ] Cost + latency tracked alongside quality
