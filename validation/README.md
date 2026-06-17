# Validation Archive

Self-contained archive of the LLM screening pipeline validation.
Everything needed to reproduce or verify the validation results is in this
directory.

**Git tag:** `v0.1-validation-complete` (2026-06-17) marks the exact repo
state when this archive was created. You can always `git checkout
v0.1-validation-complete` as an alternative way to access the full state.

---

## Results Summary

| Benchmark | Domain | Gold positives | Sensitivity | Pool size |
|-----------|--------|---------------|-------------|-----------|
| Boeckle et al. (2016) | FND neuroimaging | 25 | 25/25 (100%) | 709 |
| Ludwig et al. (2018) | Trauma/stressors in FND | 15 | 15/15 (100%) | 197 |
| **Combined** | | **40** | **40/40 (100%)** | **906** |

Model: Qwen 3.5 122B via e-INFRA MetaCentrum (`https://llm.ai.e-infra.cz/v1`)

### Criteria-ID revalidation (2026-06-17)

Prompts were updated to label each inclusion/exclusion criterion with a
stable ID (I1–I3, E1–E5/E7) and the output schema now includes
`inclusion_criteria_applied` and `exclusion_criteria_applied` arrays.
Sensitivity was re-verified on both benchmarks with identical results
(40/40, 100%). Results are in `data/criteria_ids/`.

---

## Directory Structure

```
validation/
├── README.md                  # This file
├── scripts/
│   ├── fnd_meta_search.py             # FROZEN: search script (all modes)
│   ├── llm_screen_abstracts.py        # FROZEN: LLM screening script
│   ├── validate_ludwig_recall.py      # Ludwig: match search → gold standard
│   ├── validate_os_recall.py          # Boeckle: match search → gold standard
│   ├── resolve_ludwig_references.py   # Ludwig: DOI resolution from CrossRef
│   ├── check_pilot_results.py         # Quick sensitivity check
│   ├── analyze_full_validation.py     # Deep-dive analysis of Boeckle run
│   ├── compare_human_llm.py           # Human vs LLM comparison
│   └── prepare_human_screening_sample.py
├── data/
│   ├── ludwig_included_studies.csv           # Ludwig gold standard (34 studies)
│   ├── ludwig_included_studies_resolved.csv  # With verified DOIs
│   ├── ludwig_2018_references_crossref.json  # CrossRef API cache
│   ├── ludwig_validation_set.jsonl           # 197 records, 15 gold-labeled
│   ├── ludwig_screening_results.jsonl        # Full LLM output (Ludwig)
│   ├── table_of_OS_studies.csv               # Boeckle gold standard (49 studies)
│   ├── table_of_OS_studies_resolved.csv      # With DOIs
│   ├── boeckle_2016_references_crossref.json # CrossRef API cache
│   ├── validation_screening_set.jsonl        # 709 records, 25 gold-labeled
│   ├── validation_screening_set_50.jsonl     # 50-record pilot subset
│   ├── human_screening_sample_50.csv         # Human blind screening sample
│   ├── pilot/                                # Model comparison outputs
│   │   ├── qwen3_5_122b_thinking_off_FULL-VALIDATION.jsonl
│   │   ├── qwen3_5_122b_thinking_off.jsonl
│   │   └── gemma4_thinking_off.jsonl
│   └── criteria_ids/                         # Criteria-ID revalidation (2026-06-17)
│       ├── boeckle_criteria_ids.jsonl        # 709 records, 25/25 strict
│       └── ludwig_criteria_ids.jsonl         # 197 records, 15/15 strict
├── prompts/
│   ├── neuroimaging_v1.txt    # Boeckle benchmark prompt
│   └── trauma_v1.txt          # Ludwig benchmark prompt
├── docs/
│   ├── ludwig_validation_report.md    # Ludwig search recall report
│   ├── os_validation_report.md        # Boeckle search recall report
│   ├── validation_strategy_notes.md   # Methodology and conclusions
│   └── model_comparison_run.md        # Commands for model comparison runs
└── search_runs/
    ├── boeckle_20260512/              # Full search run output (Boeckle)
    └── ludwig_20260528/               # Full search run output (Ludwig)
```

---

## How to Reproduce

### Prerequisites

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests biopython python-dotenv

export OPENAI_BASE_URL="https://llm.ai.e-infra.cz/v1"
export OPENAI_API_KEY="<your e-INFRA token>"
```

### Boeckle Benchmark (neuroimaging)

```bash
# 1. Run search (inception to Aug 2015, full production terms)
python3 validation/scripts/fnd_meta_search.py --full --auto
# (or use the archived run: validation/search_runs/boeckle_20260512/)

# 2. Build validation JSONL
python3 validation/scripts/validate_os_recall.py \
  --search-dir validation/search_runs/boeckle_20260512

# 3. Screen with LLM
OPENAI_MODEL=qwen3.5-122b python3 validation/scripts/llm_screen_abstracts.py \
  --input validation/data/validation_screening_set.jsonl \
  --output /tmp/boeckle_replication.jsonl \
  --prompt validation/prompts/neuroimaging_v1.txt \
  --workers 4 --no-response-format --no-thinking

# 4. Check sensitivity
python3 validation/scripts/check_pilot_results.py \
  /tmp/boeckle_replication.jsonl \
  --gold validation/data/validation_screening_set.jsonl
```

### Ludwig Benchmark (trauma/stressors)

```bash
# 1. Run search (inception to Nov 2016, Ludwig 3-block terms)
python3 validation/scripts/fnd_meta_search.py --ludwig_validation --auto
# (or use the archived run: validation/search_runs/ludwig_20260528/)

# 2. Build validation JSONL
python3 validation/scripts/validate_ludwig_recall.py \
  --search-dir validation/search_runs/ludwig_20260528

# 3. Screen with LLM
OPENAI_MODEL=qwen3.5-122b python3 validation/scripts/llm_screen_abstracts.py \
  --input validation/data/ludwig_validation_set.jsonl \
  --output /tmp/ludwig_replication.jsonl \
  --prompt validation/prompts/trauma_v1.txt \
  --workers 4 --no-response-format --no-thinking

# 4. Check sensitivity
python3 validation/scripts/check_pilot_results.py \
  /tmp/ludwig_replication.jsonl \
  --gold validation/data/ludwig_validation_set.jsonl
```

### Human vs LLM Comparison (Boeckle)

```bash
python3 validation/scripts/compare_human_llm.py \
  --llm validation/data/pilot/qwen3_5_122b_thinking_off_FULL-VALIDATION.jsonl \
  --human validation/data/human_screening_sample_50.csv
```

---

## Key Methodological Notes

- **Prompt development** was done on Boeckle data. Ludwig is fully held out
  (zero prompt exposure before the validation run).
- **Search term ceiling:** Ludwig's title/abstract search recovers 15/34
  studies; the other 19 require full-text search (ScienceDirect) or
  reference-chasing. This is a property of the search strategy, not a bug.
- **DOI resolver:** Uses CrossRef `key`-field lookup (not positional
  indexing). The original version had a bug producing 7 DOI collisions;
  the version in this archive is the corrected one.
- **Model settings:** `--no-thinking` (reasoning trace OFF) and
  `--no-response-format` (e-INFRA endpoint doesn't support
  `response_format=json_object`).

---

## Citation

If reporting these results, cite:
- Boeckle M et al. (2016). Neural correlates of conversion disorder. *BMC Psychiatry*, 16, 195.
- Ludwig L et al. (2018). Stressful life events and maltreatment in conversion disorder. *Lancet Psychiatry*, 5(4), 307-320.
