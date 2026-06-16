---
domain: ai-agent-engineering
description: Designing an agent harness — action space, observation formatting, and the agent loop.
---

# Harness Design

## The loop
```
observe -> decide (LLM) -> act (tool call) -> observe result -> ... -> done
```
Keep the loop dumb and the model smart. The harness's job: format observations, execute actions,
enforce limits, detect termination. Don't bake task logic into the harness.

## Action space design
- **Few, composable, orthogonal** actions beat many overlapping ones. A model picking among 5
  clear tools outperforms one with 30 fuzzy tools.
- Each action does one thing with a predictable result. Avoid actions whose behavior depends on
  hidden mode/state.
- Prefer high-level actions matching the task's natural verbs (`search_orders`,
  `refund(order_id)`) over low-level primitives the model must chain laboriously.
- Make destructive actions explicit and confirmable (see maker/checker in orchestration).

## Observation formatting
The model only knows what you put in context. Format for an LLM reader, not a log file:
```python
def format_observation(result):
    if result.error:
        return f"ERROR: {result.error}\nHint: {result.recovery_hint}"   # actionable
    rows = result.rows[:20]                       # TRUNCATE — never dump 10k rows
    more = f"\n…(+{len(result.rows)-20} more, refine your query)" if len(result.rows) > 20 else ""
    return f"{len(result.rows)} results:\n" + render_table(rows) + more
```
Principles:
- Truncate large outputs; tell the model it was truncated and how to narrow.
- Surface errors as actionable messages with a recovery hint, not raw stack traces.
- Be consistent: same action -> same observation shape every time.
- Strip noise (ANSI codes, redundant headers) that wastes tokens and confuses parsing.

## Loop control
```python
for step in range(MAX_STEPS):                 # hard cap — never unbounded
    action = model.decide(history)
    if action.name == "finish": break
    obs = execute(action)                     # with per-tool timeout
    history.append(action, obs)
    if budget.exceeded(): break               # token / cost / wall-clock budget
```
- Hard step cap + budget guard prevent runaway loops.
- Detect stuck loops (same action repeated, no state change) and break/redirect.
- Manage context: summarize or drop old turns before overflow; keep the task + recent steps.

## Pitfalls
- Dumping raw tool output into context -> blows the window, buries signal.
- Overlapping/ambiguous tools -> model dithers and mis-selects.
- No step/budget cap -> infinite loops, runaway cost.
- Inconsistent observation formats -> model can't learn the pattern.
- Errors as opaque tracebacks -> model can't recover.

## Checklist
- [ ] Small, orthogonal, well-named action space
- [ ] Observations truncated, consistent, LLM-readable
- [ ] Errors actionable with recovery hints
- [ ] Hard step cap + budget guard + stuck-loop detection
- [ ] Context-window management strategy
