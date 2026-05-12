# Data

This directory holds benchmark fixtures and evaluation outputs for the LLM
screening pipeline.

## OS validation

- `table_of_OS_studies.csv` — Boeckle et al. (2016) Table 1 (49 studies),
  extracted from the original paper for cross-referencing.
- `validation_screening_set.jsonl` — All 709 deduplicated records from the
  `full` search with OS cutoff date (inception to 2015/08/31). The 33
  studies matched to OS Table 1 are pre-labeled as `include_candidate`;
  the remaining 676 have `human_gold_decision: null`.

## Pilot screening fixtures

- `test_abstracts_20.jsonl`
- `test_abstracts_20_protocol_resolved.jsonl`
- `test_abstracts_20_protocol_resolved.csv`

## Evaluation outputs

- `evaluation_summary_*.csv`
- `evaluation_disagreements_*.jsonl`

Generated raw model outputs (`llm_screening_results_*.jsonl`) and ad hoc old
result files are intentionally ignored and can be regenerated from the scripts
in `scripts/`.
