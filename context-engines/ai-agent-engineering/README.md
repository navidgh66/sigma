# Context Engine: ai-agent-engineering

Domain knowledge for **AI agent & harness engineering**.

## Scope
- Harness design (action space, observation formatting, completion-rate tuning)
- Tool definition (schemas, docs, error messages, tool-first design)
- Orchestration patterns (orchestrator-workers, routing, prompt chaining,
  parallelization, evaluator-optimizer)
- Multi-agent systems (delegation, maker/checker separation, supervision)
- Evals (task suites, rubrics, adversarial verification, regression evals)
- MCP servers (tools, resources, transport, auth)
- **Loop engineering** (automations, worktrees, skills, connectors, sub-agents,
  persistent state, ratchet effect)
- Context management (window budgeting, compaction, subagent offloading)

## Implementers
`implementers/` — harness-design, tool-definition, orchestration, multi-agent,
evals, mcp-servers, loop-engineering, context-management.

## Verifiers
`verifiers/` — tool-schema validity, eval coverage, maker/checker separation,
context-budget adherence, loop-safety (no infinite spend).

> 🚧 Seed file.
