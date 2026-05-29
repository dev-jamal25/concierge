"""Modelserver — router intent classifier (T148, T151).

Boot sequence (fail-fast):
  1. Read model_card.yaml. Exit 1 if missing or malformed.
  2. SHA-256 model.onnx vs model_card.artifact_sha256. Exit 1 on mismatch.
  3. SHA-256 vocab.json  vs model_card.vocab_sha256.  Exit 1 on mismatch.
  4. Load vocab.json.
  5. Create onnxruntime InferenceSession (CPUExecutionProvider — no GPU).
  6. Warmup inference on a single dummy token sequence.
  7. Start serving; /readyz returns 200.

No torch anywhere in this module. Image budget: <= 500 MB.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

import hvac
import numpy as np
import onnxruntime as ort
import yaml
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "")
VAULT_ADDR = os.getenv("VAULT_ADDR", "")
VAULT_TOKEN = os.getenv("VAULT_DEV_ROOT_TOKEN_ID", "")
VAULT_KV_MOUNT = os.getenv("VAULT_KV_MOUNT", "secret")
SERVICE_TOKEN_PATH = "service/internal-token"

_BASE = Path(__file__).parent
MODEL_CARD_PATH = Path(
    os.getenv("MODEL_CARD_PATH", str(_BASE / "model_card.yaml"))
)
ARTIFACTS_DIR = Path(
    os.getenv("ARTIFACTS_DIR", str(_BASE / "artifacts"))
)

LABELS: tuple[str, ...] = ("spam", "faq", "lead_intent", "escalate", "ambiguous")

logger = logging.getLogger("modelserver")

# ---------------------------------------------------------------------------
# Wire contract models
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    message: str = Field(max_length=4000)
    # Logged for observability only; the classifier is tenant-agnostic and
    # MUST NOT vary its prediction by tenant (Constitution Principle III).
    tenant_id: str | None = None


class PredictResponse(BaseModel):
    label: str
    confidence: float
    per_class: dict[str, float]
    artifact_sha256: str


# ---------------------------------------------------------------------------
# Encoder — mirrors notebooks/03_small_dl_onnx identically
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _encode(
    text: str,
    vocab: dict[str, int],
    max_len: int,
    pad_id: int,
    unk_id: int,
) -> list[int]:
    ids = [vocab.get(tok, unk_id) for tok in _tokenize(text)][:max_len]
    if len(ids) < max_len:
        ids = ids + [pad_id] * (max_len - len(ids))
    return ids


# ---------------------------------------------------------------------------
# Boot state
# ---------------------------------------------------------------------------


@dataclass
class _ModelState:
    session: ort.InferenceSession | None = None
    vocab: dict[str, int] = field(default_factory=dict)
    max_len: int = 32
    pad_id: int = 0
    unk_id: int = 1
    artifact_sha256: str = ""
    model_card_version: str = ""
    ready: bool = False


_STATE = _ModelState()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _boot() -> None:
    """Synchronous boot: verify artifacts, load model, run warmup. Exit 1 on any failure."""
    # 1 — model card
    if not MODEL_CARD_PATH.exists():
        logger.critical("model_card.yaml not found at %s", MODEL_CARD_PATH)
        sys.exit(1)
    try:
        card: dict = yaml.safe_load(MODEL_CARD_PATH.read_bytes()) or {}
    except Exception as exc:
        logger.critical("model_card.yaml parse error: %s", exc)
        sys.exit(1)

    _STATE.model_card_version = str(card.get("model_card_version", ""))

    # 2 — model.onnx integrity
    model_path = ARTIFACTS_DIR / "model.onnx"
    expected_model_sha = card.get("artifact_sha256", "")
    actual_model_sha = _sha256_file(model_path)
    if actual_model_sha != expected_model_sha:
        logger.critical(
            "model.onnx SHA-256 mismatch (expected=%s actual=%s)",
            expected_model_sha,
            actual_model_sha,
        )
        sys.exit(1)
    _STATE.artifact_sha256 = actual_model_sha

    # 3 — vocab.json integrity
    vocab_path = ARTIFACTS_DIR / "vocab.json"
    expected_vocab_sha = card.get("vocab_sha256", "")
    actual_vocab_sha = _sha256_file(vocab_path)
    if actual_vocab_sha != expected_vocab_sha:
        logger.critical(
            "vocab.json SHA-256 mismatch (expected=%s actual=%s)",
            expected_vocab_sha,
            actual_vocab_sha,
        )
        sys.exit(1)

    # 4 — load vocab
    vocab_data: dict = json.loads(vocab_path.read_bytes())
    _STATE.vocab = vocab_data["vocab"]
    _STATE.max_len = int(vocab_data.get("max_len", 32))
    _STATE.pad_id = int(vocab_data.get("pad_id", 0))
    _STATE.unk_id = int(vocab_data.get("unk_id", 1))

    # 5 — onnxruntime session (CPU only — no torch, no GPU runtime)
    _STATE.session = ort.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )

    # 6 — warmup: first inference asserts session is callable
    _infer("warmup")

    # 7 — mark ready
    _STATE.ready = True
    logger.info(
        "modelserver ready (model_card_version=%s artifact=%s...)",
        _STATE.model_card_version,
        _STATE.artifact_sha256[:12],
    )


def _infer(text: str) -> tuple[str, float, dict[str, float]]:
    """Encode text, run ONNX inference, return (label, confidence, per_class)."""
    assert _STATE.session is not None, "model not loaded"
    ids = _encode(text, _STATE.vocab, _STATE.max_len, _STATE.pad_id, _STATE.unk_id)
    input_ids = np.array([ids], dtype=np.int64)
    logits: np.ndarray = _STATE.session.run(["logits"], {"input_ids": input_ids})[0][0]
    # softmax (numerically stable)
    shifted = logits - logits.max()
    exp = np.exp(shifted)
    probs = exp / exp.sum()
    idx = int(probs.argmax())
    return (
        LABELS[idx],
        float(probs[idx]),
        {lbl: float(probs[i]) for i, lbl in enumerate(LABELS)},
    )


# ---------------------------------------------------------------------------
# Vault service-token bootstrap (mirrors guardrails sidecar — T151)
# ---------------------------------------------------------------------------


def _ensure_service_token_from_vault() -> str:
    try:
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        try:
            resp = client.secrets.kv.v2.read_secret_version(
                path=SERVICE_TOKEN_PATH,
                mount_point=VAULT_KV_MOUNT,
                raise_on_deleted_version=False,
            )
            existing = resp["data"]["data"]
        except hvac.exceptions.InvalidPath:
            existing = None
        if existing and existing.get("token"):
            return existing["token"]
        token = secrets.token_urlsafe(32)
        client.secrets.kv.v2.create_or_update_secret(
            path=SERVICE_TOKEN_PATH,
            secret={"token": token},
            mount_point=VAULT_KV_MOUNT,
        )
        return token
    except Exception:  # noqa: BLE001
        logger.exception("vault service-token fetch failed; falling back to SERVICE_TOKEN env")
        return ""


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def _require_service_token(x_service_token: str | None) -> None:
    if not SERVICE_TOKEN:
        return
    if x_service_token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="missing or invalid service token")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="concierge-modelserver", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    global SERVICE_TOKEN
    _boot()
    vault_token = _ensure_service_token_from_vault()
    if vault_token:
        SERVICE_TOKEN = vault_token
        logger.info("service token loaded from Vault (path=%s)", SERVICE_TOKEN_PATH)
    elif SERVICE_TOKEN:
        logger.warning("service token sourced from env (Vault unavailable)")
    else:
        logger.warning("no service token configured — auth disabled (dev/test only)")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — also asserts artifact hash matches model_card.yaml (T148)."""
    return {
        "status": "ok",
        "artifact_sha256": _STATE.artifact_sha256,
        "model_card_version": _STATE.model_card_version,
    }


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    if not _STATE.ready:
        raise HTTPException(status_code=503, detail="model not ready")
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    x_service_token: str | None = Header(default=None),
) -> PredictResponse:
    _require_service_token(x_service_token)
    label, confidence, per_class = _infer(request.message)
    if request.tenant_id:
        logger.info(
            "predict tenant_id=%s label=%s confidence=%.4f",
            request.tenant_id,
            label,
            confidence,
        )
    return PredictResponse(
        label=label,
        confidence=confidence,
        per_class=per_class,
        artifact_sha256=_STATE.artifact_sha256,
    )
