# LLM Screening Test Protocol

Last updated: 2026-05-06

## Purpose

Validate an LLM-assisted title/abstract screening loop before using it on the
expanded FND neuroimaging search. The first validation target is whether the
pipeline recovers likely Boeckle et al. (2016) included studies while correctly
flagging random search hits for human review or exclusion.

## What Changed Already

- `fnd_meta_search.py` now loads `.env` automatically from the repo root.
- `FND_SEARCH_MODE=os_validation` now runs a validation search approximating
  the Boeckle et al. (2016) search terms through August 2015.
- `scripts/make_screening_test_set.py` builds a 20-record JSONL test set from a
  deduplicated search CSV.
- `scripts/llm_screen_abstracts.py` screens JSONL records through any
  OpenAI-compatible `/v1/chat/completions` endpoint.
- `.env.example` documents the search and LLM API variables.

## Step 1: Set Up Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with available keys:

```bash
NCBI_EMAIL=your.email@institution.edu
NCBI_API_KEY=...
SCOPUS_API_KEY=...
WOS_API_KEY=
```

The script will skip unavailable APIs and record this in `search_log.txt`.

## Step 2: Run OS-Validation Search

```bash
FND_SEARCH_MODE=os_validation python fnd_meta_search.py
```

Expected output is a new folder:

```text
fnd_search_YYYYMMDD_HHMMSS/
```

Key files:

- `queries.json`: exact API query strings.
- `raw_<database>.csv`: pre-dedup database outputs.
- `records_deduplicated.csv`: unified deduplicated records.
- `prisma_search_metadata.json`: run metadata and counts.

Manual PsycINFO, Psyndex, Cochrane, and possibly WoS exports can be merged later;
the immediate goal is API smoke testing and LLM pipeline validation.

## Step 3: Build 20-Abstract Test Set

```bash
python scripts/make_screening_test_set.py \
  --input fnd_search_YYYYMMDD_HHMMSS/records_deduplicated.csv \
  --output data/test_abstracts_20.jsonl
```

The script tries to pick up to 8 records matching seed title/author patterns from
Boeckle-included studies and fills the rest randomly. If it reports too few OS
matches, inspect the OS-validation search output and provide a better pattern
file:

```bash
python scripts/make_screening_test_set.py \
  --input fnd_search_YYYYMMDD_HHMMSS/records_deduplicated.csv \
  --os-patterns data/os_included_patterns.txt
```

After creating the file, manually fill `human_gold_decision` for the 20 records:

- `include_candidate`
- `exclude`
- `unclear`

Keep this file as the first validation fixture.

## Step 4: Run LLM Screening

For OpenAI:

```bash
OPENAI_MODEL=gpt-4.1-mini \
python scripts/llm_screen_abstracts.py \
  --input data/test_abstracts_20.jsonl \
  --output data/llm_screening_results.jsonl
```

For LM Studio:

```bash
OPENAI_API_KEY=lm-studio \
OPENAI_BASE_URL=http://localhost:1234/v1 \
OPENAI_MODEL=local-model-name \
python scripts/llm_screen_abstracts.py \
  --input data/test_abstracts_20.jsonl \
  --output data/llm_screening_results_lmstudio.jsonl
```

If the local server rejects JSON response-format hints, add:

```bash
--no-response-format
```

Use `--workers 1` first. After JSON validity is stable, increase cautiously:

```bash
python scripts/llm_screen_abstracts.py --workers 4
```

## Step 5: Evaluate Manually

For the 20-record pilot, inspect:

- Did every response parse as JSON?
- Did known Boeckle-included records receive `include_candidate` or `unclear`,
  not `exclude`?
- Are clear non-neuroimaging or non-FND records excluded?
- Are coordinate fields mostly `unclear` unless explicitly stated?
- Are reasons short and defensible?

Do not use LLM output as final inclusion. Use it as an independent screening
signal and prioritize sensitivity.

## Evaluation

The evaluator is now implemented in `scripts/evaluate_llm_screening.py`. It
compares human labels against each model output and writes:

- `data/evaluation_summary_*.csv`
- `data/evaluation_disagreements_*.jsonl`

Use the protocol-resolved benchmark file when you want the strict screening
score:

```bash
python scripts/evaluate_llm_screening.py \
  --gold data/test_abstracts_20_protocol_resolved.jsonl
```
