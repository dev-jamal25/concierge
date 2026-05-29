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

| Route        | Share | Avg $/turn |
|--------------|-------|------------|
| spam         |  20%  | $0.000000  |
| faq          |  25%  | $0.006000/1k |
| lead_intent  |  10%  | $0.000000  |
| escalate     |  10%  | $0.000000  |
| agent        |  35%  | $3.162000/1k |

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

## Entry #1.5