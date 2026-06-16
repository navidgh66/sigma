---
domain: ai-agent-engineering
description: Writing tool schemas, descriptions, and error messages that LLMs use correctly.
---

# Tool Definition

## Anatomy of a good tool
```python
{
  "name": "search_orders",
  "description": (
    "Search orders by customer email or order ID. Returns up to 20 most recent matches. "
    "Use this BEFORE refund_order to confirm the order exists. "
    "Does NOT search by product name — use search_catalog for that."
  ),
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Customer email OR order ID (e.g. ord_123)"},
      "status": {"type": "string", "enum": ["placed","shipped","returned"],
                 "description": "Optional filter by status"},
      "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}
    },
    "required": ["query"]
  }
}
```

## Description = the model's only manual
- State **what it does, when to use it, when NOT to**, and what it returns.
- Disambiguate from sibling tools explicitly ("does not X — use Y for that"). Overlap causes misfires.
- Mention preconditions/ordering ("call search_orders first").
- Keep it tight but complete — this is high-leverage prompt real estate.

## Schema discipline
- Use `enum` for closed sets, `minimum`/`maximum` for ranges, `default` for optionals.
- Mark only truly-required fields `required`; over-requiring forces hallucinated values.
- Validate input server-side anyway — the model can and will send malformed args.
- Prefer flat, typed params over a single free-text blob the tool must parse.

## Error messages are part of the API
```python
def refund_order(order_id, amount):
    order = db.get(order_id)
    if not order:
        return {"error": f"No order '{order_id}'. Call search_orders to find the correct ID."}
    if amount > order.total:
        return {"error": f"Refund {amount} exceeds order total {order.total}. "
                         f"Max refundable: {order.total - order.refunded}."}
    ...
```
Errors must tell the model **how to fix it**: the constraint, the valid range, the next tool.
A bare `400 Bad Request` strands the agent.

## Pitfalls
- Vague descriptions ("manages orders") -> model can't choose.
- Two tools that overlap -> nondeterministic selection.
- Returning raw exceptions/HTTP codes -> no recovery path.
- Unbounded outputs -> context overflow (truncate + signal in the result).
- Stateful/hidden-mode tools -> unpredictable; keep tools pure where possible.
- Optional params not defaulted -> model invents values.

## Checklist
- [ ] Description: what / when / when-not / returns
- [ ] Disambiguated from sibling tools
- [ ] Typed schema with enums, bounds, defaults; minimal required set
- [ ] Server-side validation independent of the schema
- [ ] Errors actionable with the fix and next step
- [ ] Outputs bounded/truncated
