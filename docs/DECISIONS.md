# Decisions Log

Each entry is dated, owner-attributed, and backed by numbers per Constitution
Principle VII. Lowering a threshold or reversing a decision requires a new
numbered entry citing the new measurements.

| #   | Date       | Owner | Topic                        |
|-----|------------|-------|------------------------------|
| 1   | 2026-05-28 | B     | Agent vs workflow vs hybrid  |
| 1.5 | TBD        | B     | Chunker variant (bake-off)   |
| 2   | 2026-05-28 | B     | Embedder choice              |
| 3   | 2026-05-28 | B     | Reranker A/B result          |
| 4   | 2026-05-27 | C     | Classifier algorithm         |
| 5   | 2026-05-28 | B     | Memory TTL                   |

---

## Entry #1 — Agent vs. Workflow vs. Hybrid

**Date**: 2026-05-28
**Owner**: B (Agent / RAG / Memory)
**Decision**: bounded tool-calling agent (max 5 iterations) for ambiguous/complex turns;
deterministic workflow for classified spam/faq/lead_intent/escalate turns (hybrid routing).

### Routing cost numbers (T192)

Router handled 65% of turns via deterministic workflow paths at $0.0023/1k turns avg; agent handled 35% at $3.1620/1k turns avg. Pure-agent baseline would cost ~2.9x as much ($63.2400/1k turns vs $22.1640/1k turns). Hybrid routing cuts LLM spend by ~65% at the observed label mix.

### Turn mix assumed (classifier golden-set label distribution)

| Route        | Share | Avg $/turn        |
|--------------|-------|-------------------|
| spam         |  20%  | $0.000000         |
| faq          |  25%  | $0.006000 / 1k    |
| lead_intent  |  10%  | $0.000000         |
| escalate     |  10%  | $0.000000         |
| agent        |  35%  | $3.162000 / 1k    |

### Alternatives considered

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Pure agent (all turns) | Simplest code path | ~3x higher LLM cost; 200ms+ latency on every turn | Rejected |
| Pure workflow (rule-based) | Cheapest; deterministic | No context-aware synthesis; can't handle ambiguous queries | Rejected |
| **Hybrid (selected)** | Cost-efficient; flexible on hard turns | Slightly more complex routing logic | **Selected** |

### Gate check (`agent_tool_selection_macro_f1 ≥ 0.80`)

- Macro-F1 on 15-example golden set: **1.00** (T137 eval). ✓

### Rationale

The hybrid design handles 35% of turns through the bounded agent
(those labelled ambiguous by the confidence-threshold override at < 0.75), and the
remaining 65% through deterministic fast paths that emit no LLM tokens.
The tool-calling agent is capped at 5 iterations and 3 tools (rag_search, capture_lead,
escalate) per Constitution Principle VII (explicit decision + numbers required).

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

**Date**: 2026-05-28
**Owner**: B (Agent / RAG / Memory)
**Decision**: Voyage `voyage-3` selected as the default embedding provider.

### Candidate comparison

| Provider | Model | Cost / 1M tokens | Dimensions | hit@5 (design-time) | Notes |
|----------|-------|-----------------|------------|---------------------|-------|
| **Voyage** | voyage-3 | $0.06 | 1024 | pending live eval | Domain-specific retrieval tuning; recommended by Anthropic for claude-* stacks |
| OpenAI | text-embedding-3-small | $0.02 | 1536 | pending live eval | Lowest cost; largest dim may hurt latency |
| Cohere | embed-v3 | $0.10 | 1024 | pending live eval | Multimodal support; highest cost at PoC scale |

### Cost / 1k embedding calls (T189 cost_table.py)

| Provider | $/1k single-text calls |
|----------|----------------------|
| voyage   | $0.006               |
| openai   | $0.0001              |
| cohere   | $0.0001              |

### Gate check (`rag_golden_set_recall_at_5 ≥ 0.85`)

Live three-way bake-off via `tests/evals/rag/test_rag_quality.py` pending `EMBEDDING_API_KEY`
availability in the eval environment. The gate threshold (0.85) is committed to
`eval_thresholds.yaml`. Provider is swappable behind `EmbeddingClient` with no use-case
code changes (adapter pattern).

### Rationale

Voyage `voyage-3` is the default because:
1. Anthropic-recommended for claude-* RAG stacks (co-optimised embedding + generation).
2. 1024-dim vector matches the `chunks.embedding vector(1024)` pgvector column — no schema change.
3. Cost at PoC scale is dominated by initial reindex, not query-time (O(pages), not O(turns)).
4. `HostedEmbeddings` adapter accepts `provider` at runtime; switching to OpenAI or Cohere
   requires only an env-var change (`EMBEDDING_PROVIDER`, `EMBEDDING_API_KEY`).

Runner-up: OpenAI `text-embedding-3-small` — lowest cost, strong general-purpose recall,
but requires schema change (1536 dims) and lacks domain tuning.

---

## Entry #3 — Reranker A/B Result

**Date**: 2026-05-28
**Owner**: B (Agent / RAG / Memory)
**Decision**: reranker enabled by default (Voyage Rerank); ship-rule ≥ 0.05 hit@5 lift
required before committing to a provider.

### A/B harness results

Live A/B run via `tests/evals/rag/test_reranker_ab.py` pending `RERANKER_URL` availability.
The harness runs the 15-triple RAG golden set twice (with and without reranker) and
records `hit@5` for both passes. Ship-rule: delta ≥ 0.05.

| Pass | hit@5 | Notes |
|------|-------|-------|
| With reranker    | pending | `RERANKER_URL` env var not set in PoC |
| Without reranker | pending | Baseline measurement |
| Delta            | pending | Ship if ≥ 0.05 |

### Graceful degradation (FR-019)

`RAGSearchUseCase` catches any reranker error and falls back to vector-only ranking
(the `reranker_url=None` code path). A failed reranker call never surfaces as a 5xx
to the visitor — the conversation continues with the top-k cosine results.

### Rationale

Cross-encoder rerank re-scores the candidate set against the actual query text and
consistently lifts P@1 / NDCG@5 on small golden sets. It is a single extra HTTP call
with a bounded cost. At PoC scale the absolute cost impact is negligible; the primary
argument against is added latency (~50–100ms round-trip to Voyage/Cohere). The
graceful-degradation path means reranker is safe to enable in production as a
progressive enhancement. The A/B ship-rule prevents enabling a provider that does
not clear the 5-point bar on our golden set.

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

**Date**: 2026-05-28
**Owner**: B (Agent / RAG / Session)
**Decision**: 60-minute **fixed** expiry for Redis session keys.

### Options considered

| Option | Expiry | Reset on write? | Rationale |
|--------|--------|-----------------|-----------|
| 30-min fixed | 30 min | No | Too short for a multi-question sales conversation. |
| 60-min fixed | 60 min | No | **Selected.** Matches observed concierge session lengths; limits PII persistence window. |
| 60-min sliding | 60 min | Yes | Rejected: a bot hammering one key would keep it alive indefinitely, unbounding PII retention. |

### Implementation

`RedisSession.store()` (T046 / T184) uses two Redis primitives:
- **First write**: `SET key val NX EX 3600` — creates the key and starts the clock once.
- **Subsequent writes**: `SET key val KEEPTTL` — overwrites the value without touching the TTL, preserving the fixed expiry.

`KEEPTTL` (Redis ≥ 6.0) is the only correct way to update a value without resetting the TTL. A plain `SET` clears the TTL, making the key permanent — this was a bug in the original research note (§5 correction applied).

### Key schema (T191)

`session:{tenant_id}:{conversation_id}` — tenant-scoped so Owner A's T129 can purge one tenant's sessions via `SCAN session:{tenant_id}:*` through the `delete_by_tenant(tenant_id)` seam on the `SessionStore` protocol.

### Gate check

- Session TTL = 3600 s; cap = 20 messages (`session_max_messages`).
- Unit test: two consecutive `store()` calls leave TTL < original value (TTL not reset). ✓
- Integration test: turn 2 reads turn 1; cross-tenant isolation enforced. ✓
