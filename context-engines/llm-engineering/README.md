# Context Engine: llm-engineering

Domain knowledge for **LLM application engineering**.

## Scope
- Prompt engineering (structure, few-shot, CoT, output formatting, prompt caching)
- RAG (chunking, embeddings, retrieval, reranking, hybrid search, eval)
- Fine-tuning (when to vs RAG vs prompt, data curation, LoRA/QLoRA, DPO)
- Eval frameworks (LLM-as-judge, golden sets, regression suites, rubrics)
- Agent frameworks (LangChain, LlamaIndex, raw SDK) — when each fits
- Structured output (JSON mode, tool/function calling, schema validation)
- Cost & latency (model routing, caching, batching, streaming)
- Safety (injection defense, output validation, PII handling)

## Implementers
`implementers/` — prompt-engineering, rag, fine-tuning, evals, agent-frameworks,
structured-output, cost-latency.

## Verifiers
`verifiers/` — eval coverage, injection defense, output-schema validation,
retrieval quality, cost guardrails.

> 🚧 Seed file.
