# DECISIONS (stub — Owner B, T055)

Numbered architectural decisions made by each slice. Populated as Slice B
completes (T155–T157) and other slices append their own entries (T158).

All decisions must be backed by a number on a held-out or golden set per
Constitution Principle VII.

---

## Decision 1 — Agent vs. Workflow vs. Hybrid

*To be populated by Owner B (T155) after agent golden-set evaluation.*

Topics to cover: bounded tool-calling agent (max 5 iterations, max 2048 tokens)
vs. deterministic workflow vs. hybrid; rationale; alternatives considered;
golden-set numbers.

---

## Decision 2 — Embedding Provider

*To be populated by Owner B (T156) after RAG golden-set evaluation.*

Topics to cover: candidate comparison (Voyage vs. Cohere vs. OpenAI); cost /
recall@5 / latency tradeoffs; winner noted with runner-up scores.

---

## Decision 3 — Reranker Provider

*To be populated by Owner B (T157) after RAG golden-set evaluation.*

Topics to cover: provider candidates; +x improvement over vector-only baseline;
graceful-degradation behaviour if reranker is unavailable.

---

## Decision 4 — Classifier Algorithm

*To be populated by Owner C (T158) after three-way comparison.*

Topics to cover: classical TF-IDF / logistic regression vs. ONNX DL vs.
LLM zero-shot; winner's macro-F1, per-class F1, latency, inference cost;
rationale for deployment choice (size / speed constraint).
