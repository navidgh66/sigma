# Improving sigma's Grilling Skill: Research Report
*Generated: 2026-06-25 | Sources: ~30 (3 parallel research agents) | Confidence: High on diagnosis, Medium on transfer-to-specs*

## Executive Summary

sigma's grilling design is **already well-aligned with the evidence** — maker ≠ griller,
per-finding severity, evidence-quoting, bounded grill-loop, mechanical-only auto-edit,
surface-CRITICAL-to-human, and default-deny verdicts all match what the LLM-as-judge and
self-refinement literature recommends. The skill is not broken.

The real gains are in **four unrealized moves**: (1) a multi-family **judge panel** with
agreement-as-confidence, (2) **per-axis decomposed scoring** replacing the single holistic
READY/BLOCK verdict, (3) a **cross-round findings ledger** so the griller stops re-litigating
resolved items and "no-progress" has a stable denominator, and (4) importing **spec-kit's
six analyze categories** + a few requirements-engineering checks (singular requirements,
EARS unwanted-behaviour coverage, cross-artifact traceability) the rubric currently misses.

One housekeeping note: the skill cites **"Boonstra, 2026"** — the real author is **Lee
Boonstra** (*Spec-Driven, Production-Grade Development in the Age of Vibe Coding*), not a
2026 work. Fix the citation.

---

## 1. The current design is evidence-backed (don't change these)

| sigma rule | Backing evidence |
|---|---|
| **Maker ≠ griller** | A *distinct* critic adds independent signal; a generator has no self-discrimination edge over its own output ([SELF-IN-CORRECT](https://arxiv.org/abs/2404.04298), [LM Negotiation w/ AI Feedback](https://arxiv.org/abs/2305.10142)). Self-critique without an external agent plateaus or degrades ([LLMs Cannot Self-Correct Yet, ICLR 2024](https://arxiv.org/abs/2310.01798)). |
| **Quote the exact line as evidence** | Evidence-grounding is the mechanism that curbs hallucinated/vague critiques and "unverifiable score attribution" ([Rulers](https://arxiv.org/html/2601.08654v2); [DeCE](https://arxiv.org/abs/2509.16093)). |
| **Mechanical-only auto-edit; surface CRITICAL/intent** | Self-refinement amplifies self-bias — an editor drifts toward model-preferred phrasings, not author intent ([Pride and Prejudice](https://arxiv.org/abs/2402.11436)). Human+critic produces *fewer* hallucinated findings than critic-alone ([CriticGPT, OpenAI](https://arxiv.org/abs/2407.00215)). |
| **Bounded loop, round cap 3, no-progress stop** | Standard practice is small caps (≈3 agents/2 rounds), returns diminish and are cost-dominated ([Multiagent Debate](https://arxiv.org/abs/2305.14325)). "No-progress" is sound: consistency ≈ correctness but isn't identical, so once findings stop dropping, extra rounds re-confirm bias ([Internal Consistency survey](https://arxiv.org/abs/2407.14507)). |
| **Default to BLOCK on doubt** | Judges are systematically overconfident (cluster at 90-100% confidence, real accuracy far lower) — a skeptical default is correct ([Overconfidence in LLM-as-a-Judge](https://arxiv.org/abs/2508.06225)). |

**Takeaway:** the skill's *laws* are right. The improvements below are additive.

---

## 2. The highest-leverage change: per-axis decomposed scoring

The skill already lists 6 axes (ambiguity, hidden assumptions, testability, edge cases,
scope, ML/data risk) but emits **one holistic `VERDICT: READY|BLOCK`**. The evidence says
decompose the *score*, not just the prompt:

- DeCE (decomposed criteria-based eval) hit **Pearson r = 0.78 with expert judgment vs 0.35
  for a holistic pointwise judge** — ~2.2× better ([DeCE](https://arxiv.org/abs/2509.16093)).
- Holistic "this spec looks risky, 6/10" is the weak baseline; per-criterion pass/fail +
  evidence is the strong one.

**Concrete:** have the griller emit a **per-axis verdict line** (each axis → PASS/FAIL +
its findings), then derive the overall verdict mechanically (any axis CRITICAL/HIGH → BLOCK).
This is a small output-contract change that the gate logic in `cli/review.py` /
`hermes._grill_ready` can fold over.

---

## 3. Judge panel + agreement-as-confidence

The grill is a single agent. A **panel of disjoint model families** beats one big judge with
less intra-model/self-preference bias, at >7× lower cost ([PoLL — Replacing Judges with
Juries](https://arxiv.org/abs/2404.18796)). Self-preference bias is real and tracks
familiarity/perplexity — a same-family griller rates a fluent, model-style spec too leniently
([Self-Preference Bias, NeurIPS 2024](https://arxiv.org/abs/2410.21819)).

**But** — don't over-invest. A single well-prompted, rubric-grounded judge can match a debate
panel; the gain is conditional ([contested: Wang et al.](https://arxiv.org/abs/2402.18272) vs
[ChatEval](https://arxiv.org/abs/2308.07201)). sigma already runs multi-model research
fan-out (`cli/research.py`), so a panel grill is cheap to reach.

**Concrete:** optional panel mode — grill with 2-3 different-family models (one per axis
cluster, e.g. logic / ML-data / testability), aggregate, and **treat disagreement as low
confidence** → route to human instead of auto-BLOCK. Panel agreement *is* the calibration
signal (no separate calibration step needed).

---

## 4. Cross-round findings ledger (grill-loop)

`/grill-loop` re-grills cold each round. Without memory, the critic re-raises resolved
findings — the expected failure mode; episodic memory of prior findings is the documented fix
([Reflexion](https://arxiv.org/abs/2303.11366)). It also gives "no-progress" a **stable
denominator** instead of a fresh count each round.

**Concrete:** persist each round's findings + disposition (auto-fixed / surfaced /
dismissed-with-reason) and inject the ledger into the next grill ("do not re-litigate these").
Measure CRIT+HIGH drop *against the ledger*. The round report (`grill/{target}-r{k}.md`)
already exists — this is extending it from a log into an input.

---

## 5. Missing rubric axes (import from spec-driven frameworks)

spec-kit's `/speckit.analyze` gate is the most concretely specified checklist found — six
categories × four severities, **near 1:1 with sigma's existing tiers**
([spec-kit analyze.md](https://github.com/github/spec-kit)). The grill rubric is missing:

1. **Cross-artifact traceability** — every requirement maps to ≥1 task, every task back to a
   requirement; flag zero-coverage requirements + orphaned tasks. (sigma grills one doc; this
   is a chain check — fits the `verify` stage that already reads the full `chain.json`.)
2. **Singular-requirement check** — flag criteria hiding two behaviours in one line ("…and…",
   "…also…"). ISO/IEC/IEEE 29148's *singular* attribute; rarely caught by ambiguity-only checks.
3. **Mandatory unwanted-behaviour coverage** — require ≥1 EARS `IF…THEN`/error criterion per
   risky operation. EARS's error pattern is a structural edge-case checklist
   ([EARS](https://alistairmavin.com/ears/); [2024 template benchmark](https://link.springer.com/article/10.1007/s00766-024-00427-0) — constrained templates measurably cut ambiguity).
4. **Project "constitution" of MUST invariants** — a persistent higher-order gate above
   per-finding review (ML leakage/splits, maker≠checker, no secrets in config). sigma has these
   as conventions but not as an explicit gate the griller enforces. (spec-kit's unique idea.)
5. **Behaviour-orientation / false-sense-of-control guard** — flag a spec that is long prose /
   context dump rather than testable behaviour; agents demonstrably *ignore* prose
   ([Böckeler, martinfowler.com](https://martinfowler.com/exploring-gen-ai/sdd-3-tools.html)).
   Pair with scale-adaptive rigor (one-file change ≠ multi-PR system).

---

## Key Takeaways (ranked by leverage)

1. **Per-axis decomposed verdict** (replaces holistic READY/BLOCK) — biggest correlation gain
   (0.35→0.78), smallest code change. Do this first.
2. **Cross-round findings ledger** in `/grill-loop` — kills re-litigation, fixes the
   no-progress denominator. Cheap, high-value.
3. **Optional multi-family panel** with agreement-as-confidence — best bias reduction; sigma's
   research fan-out makes it cheap. Don't make it the default (gain is conditional).
4. **Import 5 missing axes** (traceability, singular, EARS error-coverage, constitution,
   behaviour-orientation) — rubric-text edits, no engine change.
5. **Fix the "Boonstra, 2026" citation** → Lee Boonstra.

## Methodology

Three parallel research agents (WebSearch + WebFetch), one per sub-question:
LLM-as-judge failure modes & mitigations; spec-driven-dev quality gates; adversarial/iterative
critique loops. Grounded against the live `skills/sigma-grilling/SKILL.md` +
`skills/sigma-grill-loop/SKILL.md`.

**Confidence caveats:** Most critique-loop evidence is on reasoning/code/planning, NOT specs —
[Valmeekam (planning)](https://arxiv.org/abs/2310.08118) is the closest analog; spec transfer
is reasoned inference. Two cited preprints are forward-dated (Rulers `2601.*`) — verify before
external use. "Multi-agent beats single judge" is contested. "Pairwise vs pointwise" is
single-source.

## Sources (primary)

- [Judging the Judges: Position Bias](https://arxiv.org/abs/2406.07791)
- [Self-Preference Bias in LLM-as-a-Judge, NeurIPS 2024](https://arxiv.org/abs/2410.21819)
- [MT-Bench / LLM-as-a-Judge](https://arxiv.org/abs/2306.05685)
- [Length-Controlled AlpacaEval](https://arxiv.org/abs/2404.04475)
- [Sycophancy in LMs, Anthropic](https://arxiv.org/abs/2310.13548)
- [PoLL — Replacing Judges with Juries](https://arxiv.org/abs/2404.18796)
- [DeCE — Decomposed Criteria Eval](https://arxiv.org/abs/2509.16093)
- [CriticGPT — LLM Critics Help Catch LLM Bugs, OpenAI](https://arxiv.org/abs/2407.00215)
- [Overconfidence in LLM-as-a-Judge](https://arxiv.org/abs/2508.06225)
- [LLMs Cannot Self-Correct Reasoning Yet, ICLR 2024](https://arxiv.org/abs/2310.01798)
- [Pride and Prejudice — Self-Bias in Self-Refinement](https://arxiv.org/abs/2402.11436)
- [Can LLMs Improve by Self-critiquing Their Plans?](https://arxiv.org/abs/2310.08118)
- [When Can LLMs Correct Their Own Mistakes? TACL 2024](https://aclanthology.org/2024.tacl-1.78/)
- [Reflexion, NeurIPS 2023](https://arxiv.org/abs/2303.11366)
- [Self-Refine, NeurIPS 2023](https://arxiv.org/abs/2303.17651)
- [CRITIC, ICLR 2024](https://arxiv.org/abs/2305.11738)
- [Internal Consistency & Self-Feedback Survey](https://arxiv.org/abs/2407.14507)
- [Kiro spec best practices](https://kiro.dev/docs/specs/best-practices/)
- [GitHub spec-kit](https://github.com/github/spec-kit)
- [EARS notation](https://alistairmavin.com/ears/)
- [Requirement template benchmark, RE 2024](https://link.springer.com/article/10.1007/s00766-024-00427-0)
- [Böckeler — Understanding Spec-Driven Development](https://martinfowler.com/exploring-gen-ai/sdd-3-tools.html)
- [Sean Grove — The New Code, OpenAI](https://www.youtube.com/watch?v=8rABwKRsec4)
- [Lee Boonstra — Spec-Driven Production-Grade Development](https://www.leeboonstra.dev/images/leeboonstra-specdriven-development.pdf)
