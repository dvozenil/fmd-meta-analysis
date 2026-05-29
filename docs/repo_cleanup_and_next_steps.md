# Repo State and Next Steps

Last updated: 2026-05-28

## Current status: LLM screening validated

The screening pipeline (Qwen 3.5 122B + current prompt) is validated as
a proof of concept. See `docs/validation_strategy_notes.md` for full results.

**Key numbers:**
- 25/25 strict gold-label sensitivity (100%)
- 50-record human-vs-LLM comparison: 0 LLM misses, 72% exact agreement
- LLM acts as a liberal screener (over-includes case reports and adjacent
  populations) — acceptable for dual-screening

## Scripts and data

- `fnd_meta_search.py`: search runner (update, full, os_validation,
  ludwig_validation modes).
- `scripts/llm_screen_abstracts.py`: OpenAI-compatible screening (with
  `--thinking` / `--no-thinking` flags for hybrid models, `--prompt` for
  external prompt files).
- `scripts/validate_os_recall.py`: cross-references search results against
  Boeckle et al. (2016) Table 1 using DOI-first matching.
- `scripts/resolve_os_references.py`: fetches the OS reference list from
  CrossRef and produces the enriched `table_of_OS_studies_resolved.csv`.
- `scripts/check_pilot_results.py`: quick accuracy check for pilot runs,
  supports `--gold` for external gold labels, reports strict and broad-scope
  sensitivity separately.
- `scripts/analyze_full_validation.py`: deep-dive analysis of full
  validation results (tag distributions, population analysis, etc.).
- `scripts/prepare_human_screening_sample.py`: generates stratified
  random sample as CSV for human blind screening.
- `scripts/compare_human_llm.py`: compares human screening CSV with LLM
  decisions (confusion matrix, disagreement analysis).
- `docs/validation_strategy_notes.md`: validation results and conclusions.
- `docs/os_validation_report.md`: validation report (33/49 OS studies recovered).
- `docs/model_comparison_run.md`: ready-to-run commands for pilot model comparison.
- `docs/references/`: source PDFs.
- `data/table_of_OS_studies.csv`: original OS Table 1 (49 studies, no DOIs).
- `data/table_of_OS_studies_resolved.csv`: enriched version with DOIs from CrossRef.
- `data/boeckle_2016_references_crossref.json`: cached CrossRef reference data.
- `data/validation_screening_set.jsonl`: 709 records; 25 `include_candidate`,
  8 `include_broad_scope`, 676 unlabelled.
- `data/validation_screening_set_50.jsonl`: pilot subset (15 strict, 5 broad, 30 other).
- `data/pilot/`: model pilot outputs and full validation run.
- `data/human_screening_sample_50.csv`: generated sample for blind screening.
- `scripts/resolve_ludwig_references.py`: resolves Ludwig et al. (2018)
  included studies to DOIs via CrossRef.
- `scripts/validate_ludwig_recall.py`: cross-references search results
  against Ludwig et al. (2018) included studies using DOI-first matching.
- `data/ludwig_included_studies.csv`: 34 case-control studies from Ludwig
  et al. (2018) Table 1 / references 27–61.
- `prompts/neuroimaging_v1.txt`: externalized neuroimaging screening prompt.
- `prompts/trauma_v1.txt`: Ludwig-specific trauma/stressor screening prompt.

## Gold label categories

- `include_candidate`: strict FND neuroimaging study (motor conversion, PNES
  with brain imaging, etc.) — these must be recovered.
- `include_broad_scope`: study included by Boeckle et al. under a broader scope
  (DID, nonclinical dissociation, body dysmorphic disorder, PTSD+dissociation,
  EEG-only, syncope) — reported separately, not counted against sensitivity.

## Model comparison results

| Model | Strict sensitivity (pilot) | Full-run sensitivity | Notes |
| --- | --- | --- | --- |
| Qwen 3.5 122B (no thinking) | 9/9 (100%) | **25/25 (100%)** | Selected model |
| Gemma4 (no thinking) | 6/9 (67%) | — | 3 false exclusions |

## Methodological decisions (2026-05-21)

- **PECO refined:** P=Adults ≥18, E=FND diagnosis (all historical terms),
  C=HC (primary) / clinical controls (subgroup), O=brain structure/function
  differences in MNI/Talairach coordinates. Per Morgan et al. (2018) PECO
  and COSMOS-E guidance.
- **ALE power thresholds:** ≥20 experiments target, 17 hard floor
  (Eickhoff et al. 2016). Below threshold → narrative synthesis only.
- **DTI excluded from primary ALE:** white-matter coordinates not comparable
  to grey matter VBM/fMRI coordinates. DTI → narrative synthesis.
- **Multimodal pooling:** Separate ALEs for functional and structural GM,
  then conjunction analysis via NiMARE. Optional MACM/functional decoding.
- **Screening workflow:** Meta-analysis #1 = 2 humans + LLM (conservative
  for Q1 journals). Meta-analysis #2 = human + LLM + human adjudicator
  (justified by inter-rater data from #1).

## Scoping count (PubMed-only, 2026-05-21)

Raw PubMed counts (include reviews, case reports, non-coordinate studies).
Actual ALE-eligible ≈ 30–50% of raw after filtering.

| Category | PubMed raw | Est. ALE-eligible | vs. 20-exp threshold |
| --- | --- | --- | --- |
| Functional (fMRI/PET/SPECT) | ~173 | ~40–60 | Well above |
| Structural GM (VBM/CT) | ~43 | ~15–25 | Near/at threshold |
| DTI / white matter | ~35 | ~5–10 | Below → narrative only |
| Motor FND subgroup | ~304 | ~25–40 | Likely above |
| PNES subgroup | ~257 | ~15–25 | Borderline |

Calibration: Boeckle 2016 had 12 motor fMRI studies (to Aug 2015);
Mavroudis 2024 had 8 VBM studies with narrow terms.

## What to do next

### Immediate (search finalization)

1. **Finalize and freeze search terms.** Review the Boolean strings in
   `fnd_meta_search.py` — especially the FND terminology additions
   documented in the Notion protocol page. This is the most likely thing
   that could require prompt/criteria adjustments.
2. **Run the production search** (`--full` with no date cutoff) for the
   actual meta-analysis once terms are frozen.
3. **Set up remaining API keys** — NCBI (free), Scopus (institutional),
   WoS (institutional). PsycINFO manual search via OVID.

### Short-term (screening)

4. **Screen the production corpus.** Meta-analysis #1 uses two independent
   human screeners + LLM as verification layer.
5. **Investigate the 3 in-scope misses** from the OS validation
   (Atmaca [84], Bonilha [88], Spence [20]) via citation chasing.

### Cross-validation (in progress)

6. **Ludwig et al. (2018) cross-validation — infrastructure built.**
   The trauma-in-FND meta-analysis (Lancet Psychiatry,
   doi:10.1016/S2215-0366(18)30051-8) serves as an independent held-out
   benchmark for LLM screening generalization. Infrastructure is complete:
   search mode, gold-standard CSV, DOI resolver, validation script, and
   screening prompt. Remaining: run the pipeline end-to-end.

### Methods paper (if pursued)

7. **Model-class comparison study.** Run the same FND screening task across
   a model ladder (small local → large open → frontier mid → frontier full),
   validate on both Boeckle and Ludwig benchmarks, evaluate per
   LLM4SCREENLIT recommendations. Target: Research Synthesis Methods or
   Systematic Reviews.
