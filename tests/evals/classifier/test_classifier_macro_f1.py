"""Classifier macro-F1 eval gate (T135).

Loads `services/modelserver/model_card.yaml`, re-runs the deployed model
against the held-out test split from `notebooks/data/clinc150_mapped.csv`,
and asserts the computed macro-F1 meets the `classifier_macro_f1` threshold
in `eval_thresholds.yaml`.

CI invokes this via `make eval-classifier`. A regression (macro-F1 drops
below threshold) exits non-zero and blocks merges per constitution
Principle VI. Lowering the threshold requires a numbered DECISIONS.md entry
justifying the change with numbers.

The encoding here duplicates the regex tokenizer from
`notebooks/03_small_dl_onnx.ipynb`; T172 will lift it into a shared
serving module that both the modelserver container and this test consume.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pandas as pd
import pytest
import yaml
from sklearn.metrics import f1_score

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_CARD_PATH = PROJECT_ROOT / "services" / "modelserver" / "model_card.yaml"
THRESHOLDS_PATH = PROJECT_ROOT / "eval_thresholds.yaml"

LABELS: tuple[str, ...] = ("spam", "faq", "lead_intent", "escalate", "ambiguous")
LABEL_TO_ID = {label: idx for idx, label in enumerate(LABELS)}
ID_TO_LABEL = {idx: label for label, idx in LABEL_TO_ID.items()}

MAX_LEN = 32

# Mirror of the regex tokenizer in notebooks/03_small_dl_onnx.ipynb.
_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _encode(text: str, vocab: dict[str, int], pad_id: int, unk_id: int) -> list[int]:
    ids = [vocab.get(tok, unk_id) for tok in _tokenize(text)][:MAX_LEN]
    if len(ids) < MAX_LEN:
        ids = ids + [pad_id] * (MAX_LEN - len(ids))
    return ids


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_classifier_macro_f1_meets_threshold() -> None:
    """The deployed classifier's test-set macro-F1 must meet the published gate."""

    # --- Load contract docs ---
    model_card = yaml.safe_load(MODEL_CARD_PATH.read_text(encoding="utf-8"))
    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    threshold = float(thresholds["classifier_macro_f1"])

    # --- Verify artifact integrity (mirrors T148's boot-time check) ---
    artifact_path = PROJECT_ROOT / model_card["artifact_path"]
    vocab_path = PROJECT_ROOT / model_card["vocab_path"]
    assert artifact_path.exists(), f"deployed artifact missing: {artifact_path}"
    assert vocab_path.exists(), f"deployed vocab missing: {vocab_path}"
    assert _sha256_of(artifact_path) == model_card["artifact_sha256"], (
        "artifact SHA-256 does not match model card -- training data drift?"
    )
    assert _sha256_of(vocab_path) == model_card["vocab_sha256"], (
        "vocab SHA-256 does not match model card -- training data drift?"
    )

    # --- Load test split via the model card's dataset reference ---
    csv_path = PROJECT_ROOT / model_card["dataset"]["csv_path"]
    df = pd.read_csv(csv_path)
    test = df[df["split"] == "test"].reset_index(drop=True)
    assert len(test) > 0, f"no test rows in {csv_path}"

    # Verify the CSV hash matches the model card (catches re-mapped data).
    assert _sha256_of(csv_path) == model_card["dataset"]["sha256"], (
        "test CSV SHA-256 does not match model card dataset.sha256"
    )

    # --- Encode with the deployed vocab ---
    vocab_blob = json.loads(vocab_path.read_text(encoding="utf-8"))
    vocab = vocab_blob["vocab"]
    pad_id = int(vocab_blob.get("pad_id", 0))
    unk_id = int(vocab_blob.get("unk_id", 1))
    assert int(vocab_blob.get("max_len", MAX_LEN)) == MAX_LEN, (
        f"vocab.json max_len does not match the test's encoder ({MAX_LEN})"
    )

    encoded = np.array(
        [_encode(t, vocab, pad_id, unk_id) for t in test["text"]],
        dtype=np.int64,
    )

    # --- Run inference via the same runtime the modelserver uses ---
    session = ort.InferenceSession(str(artifact_path), providers=["CPUExecutionProvider"])
    logits = session.run(["logits"], {"input_ids": encoded})[0]
    pred_ids = logits.argmax(axis=1).tolist()
    pred_labels = [ID_TO_LABEL[i] for i in pred_ids]

    # --- Score against the threshold gate ---
    macro_f1 = f1_score(test["label"], pred_labels, labels=list(LABELS), average="macro")
    per_class = f1_score(test["label"], pred_labels, labels=list(LABELS), average=None)

    print(f"\nclassifier macro-F1 gate: {threshold:.2f}")
    print(f"deployed model:           {model_card['deployed_model']}")
    print(f"measured macro-F1:        {macro_f1:.4f}  (delta {macro_f1 - threshold:+.4f})")
    for label, score in zip(LABELS, per_class):
        print(f"  per-class {label:12s} {score:.4f}")

    assert macro_f1 >= threshold, (
        f"classifier macro-F1 regression: {macro_f1:.4f} < gate {threshold:.2f} "
        f"(deployed_model={model_card['deployed_model']}). "
        "Lower the threshold only with a numbered DECISIONS.md entry."
    )


if __name__ == "__main__":
    # Allow `python -m tests.evals.classifier.test_classifier_macro_f1`
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
