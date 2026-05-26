# Quickstart — Concierge

From a fresh clone of the repository to a visitor chatting with the
agent on a test page. Target: under 30 minutes on a developer laptop
(also the bound for Success Criterion SC-001).

---

## Prerequisites

Install on the host:

- Docker Desktop ≥ 24 (with Docker Compose v2).
- Python 3.11 (for the offline classifier training notebooks; the
  stack itself runs in containers).
- Node 20 + npm (only needed if you intend to rebuild the widget
  bundle; a prebuilt bundle ships with the API image).
- `git`, `make`.

You also need hosted-API credentials:

- An Anthropic API key.
- An embeddings-API key (one of: Voyage / Cohere / OpenAI — the
  chosen provider is set in `.env`).
- A reranker-API key (if rerank is enabled; Slice B may default this
  off for the very first run).

The stack runs Vault in dev mode locally; production deployments use
a real Vault server. No production deployment is required for v1.0.

---

## 1. Clone and configure

```bash
git clone https://github.com/<your-org>/concierge.git
cd concierge
cp .env.example .env
```

Edit `.env` to set:

| Variable | Example | Notes |
|----------|---------|-------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Required |
| `EMBEDDING_PROVIDER` | `voyage` | One of `voyage`, `cohere`, `openai` |
| `EMBEDDING_API_KEY` | `vyg-...` | Matches the chosen provider |
| `RERANK_PROVIDER` | `voyage` or `cohere` | Optional |
| `RERANK_API_KEY` | `...` | Required if `RERANK_PROVIDER` set |
| `POSTGRES_PASSWORD` | dev value | Used by compose only |
| `VAULT_DEV_ROOT_TOKEN_ID` | dev value | Vault dev mode |

`.env` is gitignored. Never commit secrets.

---

## 2. Bring up the stack

```bash
docker compose up -d
docker compose ps
```

Expect the following services healthy within ~60s:

```text
postgres        (5432)   — primary store + vector store (pgvector enabled)
redis           (6379)   — session memory
minio           (9000)   — object storage
vault           (8200)   — dev mode KV v2
modelserver     (8001)   — classifier (onnxruntime + sklearn)
guardrails      (8002)   — NeMo Guardrails sidecar
api             (8000)   — FastAPI backend
admin           (8501)   — Streamlit tenant admin UI
widget-static   (8003)   — serves /widget.js + iframe page (also via API)
```

If any service is `unhealthy`, see `RUNBOOK.md` (compose-up failure).

---

## 3. Migrate the database

```bash
make migrate          # alembic upgrade head
```

This creates every table from `data-model.md`, installs the `vector`
extension, and applies all RLS policies.

---

## 4. Bootstrap a tenant_manager and seed a demo tenant

```bash
make bootstrap-manager EMAIL=ops@your-org.example.com PASSWORD='change-me'
```

Creates the first `tenant_manager` user. (No CLI step exists in v1.0
for self-service manager signup — managers are platform staff.)

Then:

```bash
make seed-demo-tenant
```

Outputs the demo tenant's:

- `tenant_id` (UUID)
- `admin_invitation_url` — copy into a browser to set the admin
  password
- `widget_public_id`
- `embed_snippet` — copy-paste-ready `<script>` tag
- Two seeded `published` CMS pages (Refund Policy, Shipping)
- One seeded `allowed_origin = http://localhost:9090` so the test
  host page works out of the box

---

## 5. Embed the widget on the test host page

```bash
make serve-test-host         # serves tests/widget-host-example/ on :9090
```

Edit `tests/widget-host-example/index.html`, paste the
`embed_snippet` from step 4 into the indicated location, then open:

```
http://localhost:9090
```

You should see:

1. The widget bubble in the bottom-right.
2. Clicking it opens the chat with the tenant's greeting.
3. The one-line consent notice (Q5: GDPR-aligned).
4. Asking "What's your return policy?" yields an answer grounded in
   the seeded Refund Policy page within ~5 seconds (SC-006).

---

## 6. Open the admin UI

```
http://localhost:8501
```

Log in with the tenant_admin account you set up via the invitation
URL. You should see:

- The CMS view with two seeded pages (states: `published`).
- An empty Leads view.
- Settings → Persona, Theme, Origins, Guardrails (tenant rails only).
- The Embed Snippet page.

---

## 7. Run the smoke test

```bash
make smoke
```

Brings up a fresh compose stack against a clean volume, runs
migrations, seeds the demo tenant, runs one chat turn end-to-end,
and tears down. This is Slice D's CI gate — it MUST pass on every
push.

---

## 8. Run the eval gates locally

```bash
make eval                    # runs all four gates
```

Or one at a time:

```bash
make eval-classifier         # macro-F1 against held-out set
make eval-agent              # tool-selection golden set (15)
make eval-rag                # RAG golden set (15)
make eval-redteam            # injection + cross-tenant set
```

Thresholds are read from `eval_thresholds.yaml`. A failure exits
non-zero.

---

## 9. Train the classifier (offline, no torch)

The classifier ships pre-built in the modelserver image. To retrain:

```bash
python -m venv .venv && source .venv/bin/activate  # PowerShell: .venv\Scripts\Activate
pip install -r notebooks/requirements.txt
jupyter lab notebooks/
```

Run the notebooks in order:

1. `01_label_taxonomy.ipynb`
2. `02_tfidf_logreg_baseline.ipynb`
3. `03_small_dl_onnx.ipynb`
4. `04_llm_zero_shot.ipynb`
5. `05_compare_and_export.ipynb` — produces
   `services/modelserver/artifacts/model.{onnx|joblib}` and updates
   `services/modelserver/model_card.yaml` with the new artifact's
   SHA-256.

Rebuild the modelserver image:

```bash
docker compose build modelserver
docker compose up -d modelserver
```

The modelserver will refuse to start if its loaded artifact's hash
disagrees with `model_card.yaml` (Principle VII / Research §9).

---

## Common issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `widget.js` 404 in the host page | `make seed-demo-tenant` not run | Run step 4 |
| Widget loads but `/chat` returns 403 | Host origin not in `allowed_origins` | Add it via admin UI Settings → Origins |
| Modelserver `Exited (1)` immediately | Artifact hash mismatch with model_card | Rebuild image after retraining |
| Eval gate fails locally with "thresholds file missing" | Repo missing `eval_thresholds.yaml` | Check the file is at repo root |
| `/chat` returns 503 with "service temporarily unavailable" | Anthropic / embedding key invalid or quota exhausted | Re-check `.env`, retry |

See `docs/RUNBOOK.md` for the full operator playbook.
