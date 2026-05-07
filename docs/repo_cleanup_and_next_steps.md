# Repo Cleanup And Next Steps

Last updated: 2026-05-07

## What Was Cleaned

- Moved the source PDFs out of the repo root and into `docs/references/`.
- Kept the working code in the root `fnd_meta_search.py` plus `scripts/`.
- Kept the benchmark fixtures and evaluation summaries under `data/`.
- Removed generated search-run folders and stale local cache files from the working tree.
- Removed the unused `python-dateutil` dependency.

## What Remains

- `fnd_meta_search.py`: search runner with `update`, `full`, and `os_validation` modes.
- `scripts/make_screening_test_set.py`: builds the 20-item pilot screening set.
- `scripts/llm_screen_abstracts.py`: runs OpenAI-compatible screening calls.
- `scripts/evaluate_llm_screening.py`: scores model outputs against human labels.
- `docs/llm_screening_protocol.md`: execution protocol for search and screening.
- `docs/references/`: source PDFs for the original study and adjacent meta-analyses.
- `data/test_abstracts_20.jsonl`: pilot screening fixture.
- `data/test_abstracts_20_protocol_resolved.jsonl`: protocol-resolved benchmark labels.
- `data/test_abstracts_20_protocol_resolved.csv`: human-readable version of the same labels.
- `data/evaluation_summary_*.csv`: model comparison tables.
- `data/evaluation_disagreements_*.jsonl`: record-level disagreements for inspection.
- `.env.example`: local env template for API keys.

## Why This Structure

The repo now separates three things that were previously mixed together:

1. Source code and scripts.
2. Reference material and protocol notes.
3. Generated benchmark data and evaluation summaries.

That makes it easier to rerun the pipeline without carrying old search dumps and
local cache files in git.

## What To Do Next

1. Finish manual screening labels on a larger pilot set if needed.
2. Add manual WoS and PsycINFO records when institutional access is available.
3. Decide whether `unclear` in the benchmark should continue to behave as
   protocol-negative for scoring.
4. Expand the evaluator if you want per-label recall by subtype or per-model
   confusion tables.
5. If a provider keeps returning 400s, keep the same script but disable
   `response_format` and capture the raw body in the output file.
