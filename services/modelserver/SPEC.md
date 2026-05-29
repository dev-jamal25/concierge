# Modelserver — Specification

**Owner**: C (Models / Security / Guardrails)
**Status**: live. `app.py` serving with boot-time artifact hash verification (T148), X-Service-Token Vault auth (T151), and integration test (`tests/integration/test_modelserver_service_token.py`). Dockerfile + CI image-size assertion (T146/T147) pending Owner A.

The modelserver is a small HTTP service that hosts the router intent classifier. It is the only place the trained model artifact runs at request time. Keeping it lean is a constitution-level constraint (Principle IV).

## Responsibilities

1. Load the deployed model artifact at boot and verify its SHA-256 against `model_card.yaml` (T148). Exit non-zero on mismatch.
2. Mirror the training-time encoding (regex tokenizer + vocab lookup + pad/truncate to `max_len`) so inputs are encoded identically to how the model was trained.
3. Serve `POST /predict` per the wire contract in [`specs/001-concierge-platform/contracts/internal/modelserver.yaml`](../../specs/001-concierge-platform/contracts/internal/modelserver.yaml).
4. Authenticate every request with the shared `X-Service-Token` issued from Vault (T151).
5. Stay under the 500 MB image-size budget. No `torch`. No GPU runtime.

## Inputs and outputs

### `POST /predict`

Request:
```json
{ "message": "what are your hours?", "tenant_id": "uuid-here" }
```

Response:
```json
{
  "label": "faq",
  "confidence": 0.87,
  "per_class": { "spam": 0.02, "faq": 0.87, "lead_intent": 0.05, "escalate": 0.04, "ambiguous": 0.02 },
  "artifact_sha256": "6cfbc658..."
}
```

`tenant_id` is logged for observability only — the classifier is tenant-agnostic and **must not** vary its prediction by tenant. That is a deliberate isolation property (constitution Principle III: cross-tenant data does not influence routing).

### `GET /healthz`

Returns liveness + the loaded artifact's SHA-256. The hash must match `model_card.yaml`'s `artifact_sha256` or the process exits 1 at boot (T148).

### `GET /readyz`

Returns readiness once the model is loaded and the first warmup inference has run.

## Serving architecture

```
┌────────────────────────────────────────────────────────────┐
│  modelserver container (target: ≤ 500 MB)                  │
│                                                             │
│   ┌──────────────────────────────────────────────────┐     │
│   │  FastAPI / Starlette ASGI app                    │     │
│   │   - POST /predict  (auth: X-Service-Token)       │     │
│   │   - GET  /healthz  (artifact hash check)         │     │
│   │   - GET  /readyz                                 │     │
│   └────┬─────────────────────────────────────────────┘     │
│        │                                                    │
│        ▼                                                    │
│   ┌──────────────────────────────────────────────────┐     │
│   │  Encoder (mirrors notebooks/03_small_dl_onnx)    │     │
│   │   regex tokenize → vocab lookup → pad max_len=32 │     │
│   └────┬─────────────────────────────────────────────┘     │
│        │                                                    │
│        ▼                                                    │
│   ┌──────────────────────────────────────────────────┐     │
│   │  onnxruntime InferenceSession                    │     │
│   │   - loads model.onnx at boot                     │     │
│   │   - asserts SHA-256 matches model_card.yaml      │     │
│   │   - CPUExecutionProvider (no GPU runtime)        │     │
│   └──────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────┘
                  ▲
                  │  service token (Vault-issued; T151)
                  │
              FastAPI backend (Owner A / B)
```

## Artifact layout

Baked into the image at `/app/artifacts/`:

| File | Source | Purpose |
|---|---|---|
| `model.onnx` | copy of `cnn_intent.onnx` from T134 | Deployment artifact — what `onnxruntime` loads |
| `vocab.json` | copy of `cnn_vocab.json` from T132/T134 | Token → id map + `max_len`, `pad_id`, `unk_id` |
| `model_card.yaml` | written by T134 | Source of truth for hashes, dataset reference, deployment rationale |

The originals (`cnn_intent.onnx`, `cnn_vocab.json`) stay in the repo as the training-output convention; `model.*` is what production loads. Swapping models at deploy time is one file copy + a model card refresh.

## Model card schema

The card is YAML, loaded once at boot. Required fields (see [`model_card.yaml`](model_card.yaml) for the current version):

```yaml
model_card_version: "1.0"
created_at: "2026-05-27"
task: router_intent_classification
deployed_model: cnn_onnx          # one of: tfidf_logreg | cnn_onnx | llm_zeroshot
dataset:
  source: clinc/clinc_oos
  config: plus
  csv_path: notebooks/data/clinc150_mapped.csv
  sha256: <sha of mapped CSV>     # T130 emits this
candidates:                        # all comparison results (T134 writes)
  - name, macro_f1, per_class_f1, latency_ms_per_prediction,
    latency_runtime, cost_per_1k_predictions, artifact_size_kb
artifact_path: services/modelserver/artifacts/model.onnx
artifact_sha256: <sha of .onnx>    # T148 verifies at boot
vocab_path: services/modelserver/artifacts/vocab.json
vocab_sha256: <sha of vocab.json>  # T148 verifies at boot
deployment_rationale: <prose justification with numbers>
```

A new card version requires a numbered DECISIONS.md entry per Principle VII.

## Boot sequence (T148)

1. Read `model_card.yaml`. Fail to start if missing or malformed.
2. Compute `sha256(artifacts/model.onnx)`. Compare to `model_card.artifact_sha256`. Exit 1 on mismatch.
3. Compute `sha256(artifacts/vocab.json)`. Compare to `model_card.vocab_sha256`. Exit 1 on mismatch.
4. Load `vocab.json` (json.loads).
5. Create `onnxruntime.InferenceSession(model.onnx, providers=["CPUExecutionProvider"])`.
6. Warmup: encode `"warmup"` and run one inference. Asserts the session is callable.
7. Start the ASGI app. `/healthz` returns `200 {status: ok, artifact_sha256, model_card_version}`.

## Build constraints

- **No torch in the image.** The container ships `onnxruntime` (~50 MB CPU wheel) and the classical-ML lane uses `scikit-learn` + `joblib` (~30 MB). torch is a training-time dep only, lives in `backend/pyproject.toml`'s `notebooks` extra.
- **Image budget ≤ 500 MB.** Asserted in CI per T147. Base image: `python:3.11-slim` or `gcr.io/distroless/python3-debian12`.
- **Pinned deps.** Use `uv pip compile` to lock the modelserver's own requirements separately from the backend's.

## Switching models

If a future comparison flips the winner (e.g. TF-IDF beats CNN on real production data):

1. Re-run T134's compare/export notebook with the new winner.
2. It copies the new artifact to `model.onnx` (and `vocab.json` only if the model uses one).
3. The model card is rewritten with the new hashes + rationale.
4. T148's boot-time check now expects the new hashes — old containers fail to start.
5. A new DECISIONS.md entry documents the switch with numbers.

## Related tasks

| Task | Status | Notes |
|---|---|---|
| T130–T134 | done | label taxonomy → classical baseline → CNN+ONNX → comparison → export |
| T135 | done | `make eval-classifier` gate; uses the same boot-time hash checks |
| T146 | pending [A] | CI image-size assertion (Dockerfile exists; CI assertion pending) |
| T147 | pending [A] | CI image-size assertion ≤ 500 MB |
| T148 | done | boot-time artifact hash verification (app.py _boot()) |
| T151 | done | Vault-issued service credential + 401 enforcement + integration test |
| T164 | done | this document |
