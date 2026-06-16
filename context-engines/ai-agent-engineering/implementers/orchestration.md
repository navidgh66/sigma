---
domain: ai-agent-engineering
description: Multi-agent patterns — orchestrator-workers, routing, and evaluator-optimizer loops.
---

# Orchestration

## Pick the simplest pattern that works
Start with a single agent + tools. Add structure only when a single loop demonstrably fails.

| Pattern | Use when |
|---------|----------|
| Single agent | Most tasks. Default. |
| Prompt chaining | Fixed sequential subtasks (draft -> refine -> format) |
| Routing | Distinct input classes need different handling/models |
| Orchestrator-workers | Subtasks unknown until runtime; parallelizable |
| Evaluator-optimizer | Output quality improves with critique iterations |

## Routing
```python
route = classifier_llm(query)              # cheap/small model picks the lane
handler = {"refund": refund_agent, "tech": support_agent, "billing": billing_agent}[route]
return handler(query)
```
Route to specialized prompts/tools/models. Use a cheap model for the routing decision; reserve
the expensive model for the hard lane. Validate the route is in the allowed set.

## Orchestrator-workers
```python
plan = orchestrator.decompose(task)        # LLM splits into independent subtasks
results = await asyncio.gather(*[worker(s) for s in plan.subtasks])  # parallel
return orchestrator.synthesize(results)
```
- Orchestrator owns decomposition + synthesis; workers are stateless and focused.
- Parallelize only truly independent subtasks; sequence dependent ones.
- Cap fan-out; a runaway planner can spawn unbounded workers (and cost).

## Evaluator-optimizer (generate -> critique -> revise)
```python
out = generator(task)
for _ in range(MAX_ROUNDS):
    review = evaluator(task, out)          # separate agent/prompt with a rubric
    if review.passed: break
    out = generator(task, feedback=review.issues)
```
- Evaluator must be a **separate** prompt/agent with an explicit rubric (maker != checker).
- Cap rounds; track whether each round actually improves the score (else stop).
- Works best when "good" is checkable (tests pass, schema valid, rubric scored).

## Pitfalls
- Multi-agent where one agent would do -> latency, cost, coordination bugs.
- Shared mutable state between agents -> race conditions; pass messages, not pointers.
- No round/fan-out cap -> runaway cost.
- Evaluator using the same context as generator -> rubber-stamps its own work.
- Lost error propagation: a failed worker silently drops from `gather` -> handle exceptions.

## Checklist
- [ ] Simplest pattern that meets the need (default: single agent)
- [ ] Router validates output against allowed lanes
- [ ] Workers stateless; only independent work parallelized
- [ ] Evaluator separate from generator, rubric-based
- [ ] Round/fan-out/budget caps in place
- [ ] Worker failures handled, not swallowed
