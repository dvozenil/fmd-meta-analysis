# Repo Cleanup And Next Steps

Last updated: 2026-05-13

## What Was Cleaned (latest round)

- Removed old pilot outputs from before the OS table matching fix.
- Removed the 20-record test set and its evaluation artifacts (superseded by
  the 709-record validation set).
- Removed `scripts/make_screening_test_set.py` and `scripts/evaluate_llm_screening.py`.
- Renamed `*_new.jsonl` pilot files to clean names.
- Cleared `__pycache__` directories.

## What Remains

- `fnd_meta_search.py`: search runner (update, full, os_validation modes).
- `scripts/llm_screen_abstracts.py`: OpenAI-compatible screening (with
  `--thinking` / `--no-thinking` flags for hybrid models).
- `scripts/validate_os_recall.py`: cross-references search results against
  Boeckle et al. (2016) Table 1 using DOI-first matching.
- `scripts/resolve_os_references.py`: fetches the OS reference list from
  CrossRef and produces the enriched `table_of_OS_studies_resolved.csv`.
- `scripts/check_pilot_results.py`: quick accuracy check for pilot runs,
  supports `--gold` for external gold labels, reports strict and broad-scope
  sensitivity separately.
- `docs/llm_screening_protocol.md`: execution protocol for search and screening.
- `docs/model_comparison_run.md`: ready-to-run commands for pilot model comparison.
- `docs/os_validation_report.md`: validation report (33/49 OS studies recovered).
- `docs/references/`: source PDFs.
- `data/table_of_OS_studies.csv`: original OS Table 1 (49 studies, no DOIs).
- `data/table_of_OS_studies_resolved.csv`: enriched version with DOIs from CrossRef.
- `data/boeckle_2016_references_crossref.json`: cached CrossRef reference data.
- `data/validation_screening_set.jsonl`: 709 records; 25 `include_candidate`,
  8 `include_broad_scope`, 676 unlabelled.
- `data/validation_screening_set_50.jsonl`: pilot subset (15 strict, 5 broad, 30 other).
- `data/pilot/gemma4_thinking_off.jsonl`: Gemma4 pilot (67% strict sensitivity).
- `data/pilot/qwen3_5_122b_thinking_off.jsonl`: Qwen3.5-122B pilot (100% strict sensitivity).

## Gold label categories

- `include_candidate`: strict FND neuroimaging study (motor conversion, PNES
  with brain imaging, etc.) — these must be recovered.
- `include_broad_scope`: study included by Boeckle et al. under a broader scope
  (DID, nonclinical dissociation, body dysmorphic disorder, PTSD+dissociation,
  EEG-only, syncope) — reported separately, not counted against sensitivity.

## Pilot results summary

| Model | Strict sensitivity | Broad-scope found | API errors |
| --- | --- | --- | --- |
| Qwen 3.5 122B (no thinking) | 9/9 (100%) | 1/6 | 0 |
| Gemma4 (no thinking) | 6/9 (67%) | 1/6 | 2 |

Qwen 3.5 122B is the clear winner for strict FND neuroimaging screening.
Gemma4 makes 3 extra false exclusions (case-report threshold too aggressive,
SPECT modality missed, dissociative disorder misclassified as non-FND).

## What To Do Next

1. Run Qwen 3.5 122B on the full `validation_screening_set.jsonl` (709 records)
   to confirm sensitivity at scale.
2. If sensitivity holds, run the production search (`--full` with no date cutoff)
   for the actual meta-analysis.
3. Add manual WoS and PsycINFO records when institutional access is available.
4. Investigate the 3 in-scope misses from the OS validation
   (Atmaca [84], Bonilha [88], Spence [20]) via citation chasing.
