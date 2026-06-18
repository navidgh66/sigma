---
command: /weave
description: Weave the pipeline's stage artifacts into one self-contained HTML chain (+ machine manifest)
stage: weave
inputs: ["topic"]
outputs: ["sigma/specs/{date}-{slug}/chain.html", "sigma/specs/{date}-{slug}/chain.json"]
---

# /weave

Weave whichever sigma stage artifacts exist into **one self-contained HTML
chain** for human review + cross-session handoff, plus a machine manifest.

## Behavior

1. Locate the spec workspace `sigma/specs/{date}-{slug}/`.
2. Collect the present stage artifacts (research.md, proposals.md,
   architecture.md, spec.md, tasks.md — skip any that are absent; directory
   artifacts impl/ and verify/ are referenced, not inlined).
3. Emit `chain.html`: one navigable section per present stage, in pipeline
   order, cross-linked from a top table of contents. Render each artifact's
   markdown faithfully; for research, carry through citations and any
   fact-vs-inference labelling. Add a provenance footer.
4. Emit `chain.json`: a deterministic manifest — for each stage, its artifact
   path, whether it exists, byte size, citation count, and headings (file
   stages) or file count (directory stages); plus `chain_complete` / `missing`.

## Rules

- Markdown stays the source of truth. `chain.html` and `chain.json` are DERIVED
  views — deleting them never affects the pipeline.
- One intentional design direction; no generic uniform card grid or stock
  gradient hero. Include a `prefers-reduced-motion: reduce` block; animate only
  compositor-friendly properties.
- The HTML must be self-contained and open directly in a browser.

## Next

→ share the `.html`, or hand `chain.json` to a fresh session to continue.
