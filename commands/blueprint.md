---
command: /blueprint
description: Turn the chosen approach into a high-level architecture document
stage: 3
inputs: ["sigma/specs/{date}-{slug}/proposals.md", "chosen_approach"]
outputs: ["sigma/specs/{date}-{slug}/architecture.md"]
---

# /blueprint

Design the **system architecture** for the chosen approach.

## Behavior

1. Read `proposals.md` and the chosen approach.
2. Produce `architecture.md` covering:
   - Components and their single responsibilities
   - Data flow (sources → transforms → sinks; for ML: data → features → model → serving)
   - Interfaces between components (well-defined boundaries)
   - Key decisions and their rationale
   - Risks and mitigations
   - Which `sigma` domains own which components
3. Favor small, isolated, independently-testable units.

## Rules

- Each unit: what it does, how it's used, what it depends on.
- Call out coupling (CACE) for ML systems.
- Diagrams in mermaid where useful.

## Next

→ `/grill --target blueprint` (catch design/logic flaws before spec) → `/spec`
