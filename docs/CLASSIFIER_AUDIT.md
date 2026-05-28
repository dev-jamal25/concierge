# Classifier Audit And Handoff

Date: 2026-05-27
Owner: C, Models / Security / Guardrails

## Current Classifier Work

The classifier is the router for inbound visitor messages. It predicts one of:

- `spam`: drop before storage / agent spend
- `faq`: run RAG over tenant CMS content
- `lead_intent`: run lead capture
- `escalate`: flag for a human
- `ambiguous`: hand off to the bounded LLM agent

The dataset currently used is `notebooks/data/clinc150_mapped.csv`, a mapped CLINC150 public text-classification dataset. This matches the assignment requirement for a small public labeled text-classification set. It is separate from tenant CMS data.

## Current Results

| Approach | Result File | Macro-F1 | Latency | Cost / 1k | Status |
|---|---|---:|---:|---:|---|
| TF-IDF char n-grams + Logistic Regression | `notebooks/results/tfidf_logreg_results.json` | 0.8329 | 1.594 ms | 0.00 | Passes 0.80 gate |
| CNN exported to ONNX | `notebooks/results/cnn_onnx_results.json` | 0.8267 | 1.115 ms | 0.00 | Passes 0.80 gate, result file still needs ONNX-latency refresh |
| LLM zero-shot, 500-row stratified sample | `notebooks/results/llm_zeroshot_results.json` | 0.4686 | 205.626 ms | 0.0104 | Fails 0.80 gate |

Current best result is now the strengthened TF-IDF char n-gram baseline. It slightly exceeds the current CNN score on this dataset, so the final export step should compare these two carefully before choosing the shipped model.

## Findings

1. The existing TF-IDF baseline is too weak because it only uses word n-grams.
2. Short visitor messages often contain typos, partial words, and short phrases. Character n-grams usually help this kind of text classification.
3. The CNN notebook reports `cnn_onnx`, but its latency cell measures PyTorch CPU inference before export. Production uses `onnxruntime`, so the result should report ONNX latency.
4. The CNN result should include `vocab_sha256` and `onnx_match_rate` so the modelserver can verify both the artifact and the encoding vocabulary.
5. The LLM zero-shot notebook intentionally evaluates 500 rows for rate-limit/time reasons. Do not expand it unless the team explicitly accepts the runtime and API cost.

## Planned Edits In This Pass

- Update `notebooks/02_tfidf_logreg_baseline.ipynb` to compare word TF-IDF and character TF-IDF variants on the validation split, then evaluate the best variant once on the held-out test split. Done.
- Update `notebooks/03_small_dl_onnx.ipynb` so latency is measured with `onnxruntime`, and include `vocab_sha256` plus `onnx_match_rate` in the result JSON. Code updated; result file still needs notebook re-run in an environment with `onnxruntime`.
- Leave `notebooks/04_llm_zero_shot.ipynb` sample size at 500.

## Edits Made

### `notebooks/02_tfidf_logreg_baseline.ipynb`

- Replaced the single word n-gram baseline with a small validation grid:
  - `tfidf_word_1_2_logreg` with `C in [0.1, 1.0, 10.0]`
  - `tfidf_charwb_3_5_logreg` with `C in [0.3, 1.0, 3.0]`
- The selected variant is `tfidf_charwb_3_5_logreg`, `C = 3.0`.
- Refreshed `notebooks/results/tfidf_logreg_results.json`.
- Refreshed `services/modelserver/artifacts/tfidf_logreg.joblib`.

Updated result:

```json
{
  "variant": "tfidf_charwb_3_5_logreg",
  "analyzer": "char_wb",
  "ngram_range": [3, 5],
  "C": 3.0,
  "val_macro_f1": 0.9050769049782786,
  "macro_f1": 0.8328625293192131,
  "latency_ms_per_prediction": 1.5938008000084665
}
```

### `notebooks/03_small_dl_onnx.ipynb`

- Changed the latency cell so it only prepares the sample IDs.
- Moved latency measurement into the ONNX parity cell.
- The updated result JSON will include:
  - `latency_runtime: "onnxruntime_cpu"`
  - `vocab_sha256`
  - `onnx_match_rate`

This notebook was not re-run in this shell because `onnxruntime` is not installed in the available Python environment. The code should be re-run in the notebook environment that originally produced `cnn_intent.onnx`.

## Reviewer Checklist

After this pass, another agent should:

- Re-run `notebooks/02_tfidf_logreg_baseline.ipynb`.
- Confirm `notebooks/results/tfidf_logreg_results.json` records `tfidf_charwb_3_5_logreg`, `C = 3.0`, and macro-F1 around `0.8329`.
- Re-run `notebooks/03_small_dl_onnx.ipynb`.
- Confirm `notebooks/results/cnn_onnx_results.json` reports ONNX latency, `vocab_sha256`, and `onnx_match_rate`.
- Compare all result files in `notebooks/results/`.
- Choose final deployable artifact in `notebooks/05_compare_and_export.ipynb`.
