# Repo Cleanup And Next Steps

Last updated: 2026-05-12

## What Was Cleaned

- Moved the source PDFs out of the repo root and into `docs/references/`.
- Kept the working code in the root `fnd_meta_search.py` plus `scripts/`.
- Kept the benchmark fixtures and evaluation summaries under `data/`.
- Removed generated search-run folders and stale local cache files from the working tree.
- Removed the unused `python-dateutil` dependency.

## What Remains

- `fnd_meta_search.py`: search runner with `update`, `full`, `os_validation`,
  and `os_table_recall` modes.
- `scripts/make_screening_test_set.py`: builds the 20-item pilot screening set.
- `scripts/llm_screen_abstracts.py`: runs OpenAI-compatible screening calls.
- `scripts/evaluate_llm_screening.py`: scores model outputs against human labels.
- `scripts/validate_os_recall.py`: cross-references search results against
  Boeckle et al. (2016) Table 1; produces a validation report and a JSONL
  screening set with known OS includes marked.
- `docs/llm_screening_protocol.md`: execution protocol for search and screening.
- `docs/os_validation_report.md`: full validation report showing 33/35
  in-scope studies recovered from the OS table.
- `docs/references/`: source PDFs for the original study and adjacent meta-analyses.
- `data/table_of_OS_studies.csv`: extracted Table 1 from the OS (49 studies).
- `data/validation_screening_set.jsonl`: 709 records with 33 OS matches marked
  as `include_candidate` for LLM pipeline sensitivity testing.
- `data/test_abstracts_20.jsonl`: pilot screening fixture.
- `data/test_abstracts_20_protocol_resolved.jsonl`: protocol-resolved benchmark labels.
- `data/test_abstracts_20_protocol_resolved.csv`: human-readable version of the same labels.
- `data/evaluation_summary_*.csv`: model comparison tables.
- `data/evaluation_disagreements_*.jsonl`: record-level disagreements for inspection.
- `.env.example`: local env template for API keys.

## What To Do Next

1. Run LLM screening on `data/validation_screening_set.jsonl` (709 records)
   and evaluate sensitivity on the 33 known OS includes.
2. If sensitivity is acceptable, run the production search
   (`--full` or `--update` with no cutoff date) for the actual meta-analysis.
3. Add manual WoS and PsycINFO records when institutional access is available.
4. Decide whether `unclear` in the benchmark should continue to behave as
   protocol-negative for scoring.
5. Expand the evaluator if you want per-label recall by subtype or per-model
   confusion tables.
6. Investigate the 2 in-scope misses (Atmaca [84], Bonilha [88]) via
   citation chasing to ensure coverage.
