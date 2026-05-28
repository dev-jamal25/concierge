# Evals as Gates

**Owner**: C (Models / Security / Guardrails) for this doc; per-gate ownership called out below.
**Constitution reference**: Principle VI — Evals as CI Gates (NON-NEGOTIABLE).

The system enforces four evaluation gates on every PR. Any single gate failing below threshold blocks the merge. Lowering a threshold requires a numbered entry in [`DECISIONS.md`](DECISIONS.md) that cites the new measurement.

The thresholds are committed in [`eval_thresholds.yaml`](../eval_thresholds.yaml):

```yaml
classifier_macro_f1:                  0.80
agent_tool_selection_macro_f1:        0.80
rag_golden_set_recall_at_5:           0.85
rag_golden_set_answer_grounded_rate:  0.85
cross_tenant_redteam_success_rate:    1.0   # zero leakage tolerated
injection_redteam_success_rate:       0.95
pii_redaction_rate:                   1.0   # zero leakage tolerated
```

## How to run locally

| Gate | Command | Owner |
|---|---|---|
| Classifier macro-F1 | `make eval-classifier` | C — **wired** |
| Agent tool-selection | `make eval-agent` | B — pending T137 |
| RAG golden set | `make eval-rag` | B — pending T139 |
| Red-team (injection + cross-tenant) | `make eval-redteam` | C — pending T142 |

Each target eventually invokes pytest under `tests/evals/<gate>/`. The classifier path is the reference pattern (see below); the others mirror its structure.

## Gate 1 — Classifier macro-F1

**File**: [`tests/evals/classifier/test_classifier_macro_f1.py`](../tests/evals/classifier/test_classifier_macro_f1.py)
**Threshold**: `classifier_macro_f1 ≥ 0.80`
**Status**: PASSING (measured 0.8267 on `cnn_onnx`)

What it does (T135):
1. Loads [`services/modelserver/model_card.yaml`](../services/modelserver/model_card.yaml).
2. Verifies the deployed `model.onnx`, `vocab.json`, and training CSV all match the SHA-256 hashes pinned in the model card (drift detector — same check T148 does at boot).
3. Encodes the held-out test split from `notebooks/data/clinc150_mapped.csv` using the deployed vocab + the T132 regex tokenizer.
4. Runs inference via `onnxruntime.InferenceSession` against the deployed `model.onnx`.
5. Computes macro-F1 + per-class F1.
6. Asserts macro-F1 ≥ 0.80; prints per-class detail; exits non-zero on regression.

How the input is built:
- Source: CLINC150 `plus` config (HuggingFace `clinc/clinc_oos`).
- Mapping: notebook [`01_label_taxonomy.ipynb`](../notebooks/01_label_taxonomy.ipynb) collapses 44 in-scope CLINC intents + the OOS class into the 5-label taxonomy.
- Splits: 5,310 train / 960 val / 1,530 test (after class-stratified mapping; oos contributes 250 train / 100 val / 1,000 test by CLINC's adversarial design).

How to interpret the per-class numbers: the `spam` class is the hardest because CLINC's `plus` test split is deliberately spam-heavy (44% of the 2,290 test rows are OOS by design). A per-class score above 0.70 for `spam` means the encoder can recognize OOS shapes; the in-scope classes routinely score 0.85+.

If the gate fails, options in order of cost:
1. Re-tune the deployed candidate (TF-IDF C grid; CNN epochs / learning rate).
2. Re-run the three-baseline comparison ([`notebooks/05_compare_and_export.ipynb`](../notebooks/05_compare_and_export.ipynb)) to confirm the winner is still the winner under the new conditions.
3. If both fail, file a DECISIONS.md entry justifying a temporary threshold reduction with concrete next-step measurements.

## Gate 2 — Agent tool-selection macro-F1

**Files (pending Owner B)**: `tests/evals/agent_tool_selection/golden.jsonl` (T136) + `test_tool_selection.py` (T137)
**Threshold**: `agent_tool_selection_macro_f1 ≥ 0.80`

The golden set is ~15 curated visitor messages where the agent's tool choice is hand-labeled (`rag_search` / `capture_lead` / `escalate`). The test sends each through the agent and scores its tool-call decision against the label.

This is **distinct from the classifier macro-F1** above: the classifier picks a routing intent label; the agent then chooses a tool. Both can be right while the other is wrong (e.g. classifier says `faq` but the agent runs `escalate` because retrieval returned nothing useful).

## Gate 3 — RAG golden set

**Files (pending Owner B)**: `tests/evals/rag/golden.jsonl` (T138) + `test_rag.py` (T139)
**Thresholds**:
- `rag_golden_set_recall_at_5 ≥ 0.85` — the expected document is in the top-5 retrieved chunks
- `rag_golden_set_answer_grounded_rate ≥ 0.85` — the agent's answer is grounded in the retrieved chunks

The golden set is ~15 (query, expected-chunk, expected-answer) triples per tenant template. `recall@5` measures retrieval; `answer_grounded_rate` measures whether the agent uses retrieval results faithfully (no hallucination).

## Gate 4 — Red-team set

**Files (pending Owner C, Docker-gated)**:
- [`tests/evals/redteam/injection.jsonl`](../tests/evals/redteam/) (T140) — prompt-injection probes
- [`tests/evals/redteam/cross_tenant.jsonl`](../tests/evals/redteam/) (T141) — cross-tenant probes
- `test_redteam.py` (T142) — runs both
- `test_pii_canary.py` (T143) — synthetic PII never appears unredacted in logs / traces / Redis / LLM input

**Thresholds**:
- `injection_redteam_success_rate ≥ 0.95` (some probes will hit; the gate is on the rate, not perfection)
- `cross_tenant_redteam_success_rate = 1.0` (NON-NEGOTIABLE per Principle III — zero leakage tolerated)
- `pii_redaction_rate = 1.0` (NON-NEGOTIABLE per Principle V — zero leakage tolerated)

The red-team gate tests the guardrails sidecar (T172) as well as the full request path. It is Docker-gated because the probes traverse the live FastAPI + Postgres + Redis + sidecar stack.

## CI integration

Owner D ([`T145`](../specs/001-concierge-platform/tasks.md)) will update [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) to invoke each gate's `make eval-*` target as a separate required check. Until then, gates 1–4 are runnable locally via the Makefile but not enforced in CI. Gate 1 is the only one currently wired and passing.

## Adding a new gate

1. Pick a threshold name and value; add to `eval_thresholds.yaml` with a comment explaining what it measures.
2. Create `tests/evals/<gate_name>/test_<gate_name>.py` that loads the threshold from the YAML, computes the metric, asserts.
3. Add a `make eval-<gate_name>` target that runs only that test.
4. Add a CI job that runs the make target.
5. Write a DECISIONS.md entry the first time the gate runs, citing the chosen threshold value with the numbers that justify it.
