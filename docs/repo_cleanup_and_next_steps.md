# Repo State and Next Steps

Last updated: 2026-06-10

## Current status: LLM screening validated (dual benchmark)

The screening pipeline (Qwen 3.5 122B + domain-specific prompts) is validated
on two independent benchmarks.

**Boeckle benchmark (neuroimaging):**
- 25/25 strict gold-label sensitivity (100%)
- 50-record human-vs-LLM comparison: 0 LLM misses, 72% exact agreement
- LLM acts as a liberal screener (over-includes case reports and adjacent
  populations) — acceptable for dual-screening

**Ludwig benchmark (trauma/stressors in FND):**
- 15/15 findable gold-label sensitivity (100%)
- 197-record pool, 65 included by LLM (33%), 132 excluded
- Search recovered 15/34 Ludwig studies (the other 19 require full-text
  search or reference-chasing — unfindable via title/abstract)
- Independently validates generalization across FND sub-domains

## Scripts and data (production)

- `fnd_meta_search.py`: search runner (update, full, os_validation,
  ludwig_validation modes).
- `scripts/llm_screen_abstracts.py`: OpenAI-compatible screening (with
  `--thinking` / `--no-thinking` flags for hybrid models, `--prompt` for
  external prompt files).
- `prompts/neuroimaging_v1.txt`: production neuroimaging screening prompt.
- `docs/references/`: source PDFs and literature reviews.

All validation-specific scripts, data, prompts, and reports are now in
`validation/`. See `validation/README.md` for the full inventory.

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
   that could require prompt/criteria adjustments. Current open decision:
   whether to replace the compact FND block with the expert-expanded block
   covering functional/psychogenic motor phenomena, PNES/FDS/NEAD, vestibular
   terms such as PPPD, and legacy terms. Do not add chronic fatigue / ME-CFS
   terms unless the protocol scope is deliberately broadened beyond FND.
2. **Run the production search** (`--full` with no date cutoff) for the
   actual meta-analysis once terms are frozen.
3. **Set up remaining API keys** — NCBI (free), Scopus (institutional),
   WoS (institutional). PsycINFO manual search via OVID. If WoS API access is
   unavailable or lacks abstracts, run WoS manually and merge the CSV export
   with `scripts/merge_external_records.py` before deduplication/screening.

### Short-term (screening)

4. **Screen the production corpus.** Meta-analysis #1 uses two independent
   human screeners + LLM as verification layer.
5. **Investigate the 3 in-scope misses** from the OS validation
   (Atmaca [84], Bonilha [88], Spence [20]) via citation chasing.

### Cross-validation (complete)

6. **Ludwig et al. (2018) cross-validation — complete.**
   The trauma-in-FND meta-analysis (Lancet Psychiatry,
   doi:10.1016/S2215-0366(18)30051-8) serves as an independent held-out
   benchmark for LLM screening generalization.
   - Search: 197 deduplicated records, 15/34 Ludwig studies matched
     (19 unfindable via title/abstract — terms only in full text)
   - LLM screening: **15/15 = 100% sensitivity** (Qwen 3.5 122B,
     `prompts/trauma_v1.txt`, `--no-thinking`)
   - 65/197 included by LLM (33% inclusion rate — higher than Boeckle
     because Ludwig search terms are narrower/more topical)
   - DOI resolver rewritten to use CrossRef key-based lookup
     (original positional indexing caused 7 collision errors)

### Methods paper (if pursued)

7. **Model-class comparison study.** Run the same FND screening task across
   a model ladder (small local → large open → frontier mid → frontier full),
   validate on both Boeckle and Ludwig benchmarks, evaluate per
   LLM4SCREENLIT recommendations. Target: Research Synthesis Methods or
   Systematic Reviews.

## Validation archive

All validation data, scripts, prompts, search runs, and LLM outputs are
archived in `validation/` as a self-contained reproduction package. See
`validation/README.md` for full reproduction instructions.

The git tag `v0.1-validation-complete` marks the exact repo state when
validation was finalized. When production work begins, validation modes
may be removed from the main scripts; the `validation/` folder retains
frozen copies of everything needed to re-run independently.
