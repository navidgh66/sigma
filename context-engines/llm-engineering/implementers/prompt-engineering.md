---
domain: llm-engineering
description: Prompt structure, few-shot, chain-of-thought, and prompt caching for reliable LLM outputs.
---

# Prompt Engineering

## Structure (the reliable skeleton)
```
[System] role + task + constraints + output format
[Context] retrieved docs / data, clearly delimited
[Few-shot] 1-5 input->output exemplars (optional)
[Task] the actual request
```
Put stable, reusable content (system prompt, instructions, big context) FIRST — it caches better
and anchors behavior. Put the variable query LAST.

## Be specific and bound the output
```python
system = """You are a support classifier. Classify each ticket into exactly one of:
billing, technical, account, other. Respond ONLY with the JSON: {"label": "<one>"}.
If unclear, use "other". Do not explain."""
```
- State the exact output format and forbid extras. Ambiguity -> drift.
- Use delimiters (XML tags, ```fences) to separate instructions from data — prevents the model
  treating pasted content as instructions (also a light injection guard).
- Prefer "do X" over "don't do Y"; positive instructions are followed more reliably.

## Few-shot
- Use when the task has a specific format/style hard to describe in prose.
- Make exemplars cover edge cases and the hard classes, not just easy ones.
- Keep label distribution sane (don't bias by ordering all positives first).
- Diminishing returns past ~5 examples; long exemplars eat context + cost.

## Chain-of-thought (CoT)
```python
"Think step by step, then give your final answer after 'ANSWER:'."
```
- Helps on multi-step reasoning/math/logic. Parse only the part after the marker.
- For latency/cost-sensitive paths, keep reasoning hidden (separate field) or skip CoT on easy tasks.
- Structured CoT (numbered steps) beats vague "think carefully".

## Prompt caching (Anthropic / OpenAI)
```python
# Anthropic: mark the long stable prefix as cacheable
messages=[{"role":"user","content":[
    {"type":"text","text": big_system_context, "cache_control":{"type":"ephemeral"}},
    {"type":"text","text": user_query},
]}]
```
- Cache the large, unchanging prefix (system prompt, tool defs, big context). 5-10x cheaper +
  faster on cache hits.
- Order matters: cached content must be a stable prefix; put volatile content after it.

## Pitfalls
- Vague format spec -> unparseable output. Always pin the schema.
- Instructions mixed with untrusted data, no delimiters -> injection + confusion.
- Over-long few-shot -> cost + context bloat with little gain.
- CoT on trivial tasks -> wasted tokens/latency.
- Volatile content before cached prefix -> cache never hits.

## Checklist
- [ ] Output format explicitly pinned; extras forbidden
- [ ] Instructions vs data delimited
- [ ] Few-shot only when format-by-example helps; edge cases covered
- [ ] CoT reserved for genuine reasoning; final answer marked for parsing
- [ ] Stable prefix cached; volatile query last
