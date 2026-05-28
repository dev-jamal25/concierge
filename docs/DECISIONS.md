# Decisions Log

Each entry is dated, owner-attributed, and backed by numbers per Constitution
Principle VII. Lowering a threshold or reversing a decision requires a new
numbered entry citing the new measurements.

| #   | Date       | Owner | Topic                        |
|-----|------------|-------|------------------------------|
| 1   | TBD        | B     | Agent vs workflow vs hybrid  |
| 1.5 | TBD        | B     | Chunker variant (bake-off)   |
| 2   | TBD        | B     | Embedder choice              |
| 3   | TBD        | B     | Reranker A/B result          |
| 4   | 2026-05-27 | C     | Classifier algorithm         |
| 5   | TBD        | B     | Memory TTL                   |

---

## Entry #1 — Agent vs. Workflow vs. Hybrid

*To be populated by Owner B (T155) after agent golden-set evaluation.*

Topics to cover: bounded tool-calling agent (max 5 iterations, max 2048 tokens)
vs. deterministic workflow vs. hybrid; rationale; alternatives considered;
golden-set numbers (`agent_tool_selection_macro_f1 ≥ 0.80`).

---

## Entry #1.5 — Chunker variant

*To be populated by Owner B (T182) after three-way bake-off on 15-triple RAG golden set.*

Topics to cover: fixed-size baseline (500-token, no overlap) vs. paragraph-aware
recursive (400/50/600) vs. header-first recursive (full heading path prepended).
Metrics: `hit@5`, `MRR`, mean retrieval latency (ms). Winner = highest `hit@5`
satisfying `rag_golden_set_recall_at_5 ≥ 0.85` AND latency ≤ 200ms p95; ties
broken by `MRR` then latency.

---

## Entry #2 — Embedding Provider

*To be populated by Owner B (T156) after RAG golden-set evaluation.*

Topics to cover: candidate comparison (Voyage vs. Cohere vs. OpenAI); cost /
recall@5 / latency tradeoffs; winner noted with runner-up scores.

---

## Entry #3 — Reranker A/B Result

*To be populated by Owner B (T157 / T183) after A/B harness run on 15-triple golden set.*

Topics to cover: `hit@5` with reranker enabled vs. disabled; delta vs. 0.05
ship-rule threshold; provider candidates if reranker ships; graceful-degradation
behaviour if disabled. FR-019 fallback note if reranker is disabled (query
rewriting already live).

---

## Entry #4 — Classifier Algorithm

**Date**: 2026-05-27
**Owner**: C (Models / Security / Guardrails)
**Decision**: deploy `cnn_onnx` (1D-CNN + word embeddings, exported to ONNX) as the router-intent classifier.

### Accuracy comparison

| model        |   macro_f1 |   f1_spam |   f1_faq |   f1_lead_intent |   f1_escalate |   f1_ambiguous |
|:-------------|-----------:|----------:|---------:|-----------------:|--------------:|---------------:|
| tfidf_logreg |     0.8329 |    0.7514 |   0.7982 |           0.831  |        0.9357 |         0.8481 |
| cnn_onnx     |     0.8267 |    0.7523 |   0.7788 |           0.8042 |        0.9052 |         0.8931 |
| llm_zeroshot |     0.4686 |    0.0577 |   0.4644 |           0.5093 |        0.6832 |         0.6286 |

### Operational comparison

| model        |   latency_ms_per_prediction | latency_runtime   |   cost_per_1k_predictions |   artifact_size_kb |
|:-------------|----------------------------:|:------------------|--------------------------:|-------------------:|
| tfidf_logreg |                       1.594 | sklearn_cpu       |                    0      |              711.1 |
| cnn_onnx     |                       0.083 | onnxruntime_cpu   |                    0      |              455.6 |
| llm_zeroshot |                     205.626 | groq_api          |                    0.0104 |              nan   |

### Gate check (`classifier_macro_f1 ≥ 0.80`)

- `tfidf_logreg` macro_f1=0.8329 → **PASS**
- `cnn_onnx` macro_f1=0.8267 → **PASS**
- `llm_zeroshot` macro_f1=0.4686 → **FAIL**

### Rationale

CNN+ONNX is the only candidate above the 0.80 macro-F1 threshold and delivers ~19x lower serving latency than TF-IDF at onnxruntime runtime; the 0.006 macro-F1 gap does not justify the latency penalty on a per-request path. TF-IDF char n-gram is the simpler fallback if ops simplicity ever outweighs latency. LLM zero-shot ruled out: 0.47 macro-F1 vs 0.80 threshold, 200x slower, costs money.

**TF-IDF char n-gram** stays the documented fallback: same accuracy band, no vocab side-file, simpler serving path. If the modelserver image budget or onnxruntime ops cost ever changes, switching back is a one-file swap.

**LLM zero-shot (Groq llama-3.1-8b-instant)** is ruled out as a deployment candidate: macro_f1 0.4686 sits 36 points below the gate, spam recall collapses to 3% (the 'helpful zero-shot' failure mode), latency is 206 ms vs 0.083 ms for the CNN (~2500x), and it costs $0.01 per 1k predictions vs $0. It remains useful as an upper-bound diagnostic, not a serving path.

### Artifacts

- `services/modelserver/artifacts/model.onnx` — sha256 `6cfbc65825235efc576a35dec062a116078cd229dad82bddf7c402db6fabe437`
- `services/modelserver/artifacts/vocab.json` — sha256 `ac00cac61e2f8fce37607cde73bb3ba65a643015e4b99dc5ce8ecaf049bc0996`
- Training data: `notebooks/data/clinc150_mapped.csv` — sha256 `b3d6ec9b0ece4493f7d22d7d8f150acb423e2172f4221fb0837ef17e96c95f27`

---

## Entry #5 — Memory TTL

*To be populated by Owner B (T184) after implementing 60-min fixed-expiry in `redis_session.py`.*

Topics to cover: 30 min vs. 60 min; fixed vs. sliding expiry; rationale
(concierge session length expectations, blast-radius bound on token compromise,
PII already redacted before write).
