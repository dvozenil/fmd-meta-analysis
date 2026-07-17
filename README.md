# FND Neuroimaging Meta-Analysis

Updated and extended meta-analysis of neuroimaging findings in Functional Neurological Disorder (FND), building on [Boeckle et al. (2016)](https://doi.org/10.1186/s12888-016-0890-x).

## Project overview

| | |
|---|---|
| **PI** | Petr Sojka |
| **Student lead** | David Voženílek |
| **GitHub** | [dvozenil/fmd-meta-analysis](https://github.com/dvozenil/fmd-meta-analysis) |
| **Notion** | [Project hub](https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d) · [Protocol](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f) |
| **Status** | Search pipeline ready — production search next |

## What this extends

Boeckle et al. (2016) conducted an ALE meta-analysis of **functional** neuroimaging in **motor** conversion disorder, including 12 studies (187 subjects). This update:

- Extends the search window from August 2015 to present
- Broadens scope to **all FND subtypes** (motor, sensory, PNES, mixed)
- Adds a **structural neuroimaging** ALE track (VBM, cortical thickness, DTI) — searched from inception
- Uses updated FND/DSM-5/ICD-11 terminology
- Follows **PRISMA 2020** guidelines with pre-registration on PROSPERO
- Uses **NiMARE** (Python) for ALE analysis

## Repository contents

```
fnd_meta_search.py              # PRISMA-compliant API search script (PubMed, Europe PMC, WoS, Scopus)
dedup_asysd.py                  # ASySD-class deduplication algorithm (author + abstract similarity)
requirements.txt               # Python dependencies
.env.example                    # Template for API keys and LLM config
prompts/
  neuroimaging_v1.txt           # Production neuroimaging screening prompt
scripts/
  llm_screen_abstracts.py      # LLM title/abstract screening (OpenAI-compatible)
docs/
  prospero_protocol_neuroimaging.md   # Full PRISMA-P protocol (40 PROSPERO fields)
  repo_cleanup_and_next_steps.md      # Current status and roadmap
  methods_paper_plan.md               # Model-comparison methods paper design
  llm_screening_protocol.md           # Screening execution protocol
  references/                         # Literature reviews and source PDFs
tests/
  test_scopus_parse.py          # Scopus parser unit tests
test_dedup_asysd.py             # ASySD deduplication unit tests
validation/                     # Self-contained validation archive
  README.md                      # Full reproduction instructions
  scripts/                       # Frozen scripts (search, screener, validators)
  data/                          # Gold standards, screening results, pilots
  prompts/                       # Prompts used (neuroimaging + trauma)
  search_runs/                   # Archived search outputs (Boeckle + Ludwig)
  docs/                          # Validation reports
```

Source PDFs are kept locally in [docs/references/](docs/references/README.md) and are not versioned.

## Search script

`fnd_meta_search.py` queries PubMed, Europe PMC, Web of Science, and Scopus via their APIs. PsycINFO is searched manually (no REST API).

### Database coverage

| Database | API | Access | Abstracts |
|---|---|---|---|
| **PubMed** | NCBI E-utilities | Free (API key recommended for 10 req/s) | Included in search results |
| **Europe PMC** | REST API | Free, no key needed | Included in search results |
| **Scopus** | Elsevier API | Requires `SCOPUS_API_KEY` | Fetched via Abstract Retrieval API (second pass) |
| **Web of Science** | Clarivate API | Requires institutional license (`WOS_API_KEY`) | If key present; otherwise manual |
| **PsycINFO** | No REST API | Manual via Ovid/EBSCOhost | Manual export |

When API keys are missing, the script skips those databases gracefully and generates manual query files for copy-paste use.

### Search modes

```bash
# Functional track: 2015 onward (updating the original study)
python fnd_meta_search.py --update

# Structural track: inception to present (no prior comprehensive ALE)
python fnd_meta_search.py --full

# Validation: approximate Boeckle et al. (2016) terms to August 2015
python fnd_meta_search.py --os_validation

# Table recall: broadened terms for OS Table 1 recovery (reference only)
python fnd_meta_search.py --os_table_recall

# Ludwig et al. (2018) cross-validation: 3-block query to Nov 2016
python fnd_meta_search.py --ludwig_validation

# Non-interactive mode (skip confirmation prompts)
python fnd_meta_search.py --full --auto

# Choose deduplication algorithm (default: asysd)
python fnd_meta_search.py --full --dedup asysd   # ASySD-class (author + abstract similarity)
python fnd_meta_search.py --full --dedup simple   # DOI + title-hash only
```

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Put API keys in .env at the repo root. Start from:
cp .env.example .env
```

The search script loads `.env` automatically. Required keys:

| Variable | Required for | Notes |
|---|---|---|
| `NCBI_EMAIL` | PubMed | NCBI requires a contact email; API key optional (10 req/s vs 3 req/s) |
| `SCOPUS_API_KEY` | Scopus | Elsevier Developer Portal; also enables abstract + full author retrieval |
| `WOS_API_KEY` | Web of Science | Requires institutional WoS license; rarely available — script generates manual query file instead |

### Scopus abstract enrichment

The Scopus API returns metadata in the search response but may not include abstracts depending on the API key's entitlement level (STANDARD vs COMPLETE view). The script handles this with a two-stage pipeline:

1. **Search** — retrieves bibliographic metadata (title, DOI, year, journal, first author)
2. **Abstract Retrieval** — fetches full abstracts and complete author lists for records missing them, using the Elsevier Abstract Retrieval API with automatic view probing (`META_ABS → META → FULL`)

When using ASySD deduplication (default), enrichment runs **before** dedup so the similarity matcher has abstracts and full author lists to work with. Rate-limited at 0.35s between calls.

### Deduplication

Two algorithms are available:

- **ASySD-class** (`--dedup asysd`, default): Uses `rapidfuzz` fuzzy string matching on author lists and abstracts to detect duplicates across databases, plus DOI matching. Handles cross-database duplicates (e.g., PubMed/Scopus overlap) that simple DOI matching misses when DOIs are absent.
- **Simple** (`--dedup simple`): DOI-normalized match + title+year hash. Faster but misses records without DOIs or with variant titles.

### Output

Each run creates a timestamped folder (`fnd_search_YYYYMMDD_HHMMSS/`) containing:

- `queries.json` — exact Boolean strings used (reproducibility anchor)
- `raw_<database>.csv` — per-database results before dedup
- `records_deduplicated.csv` — unified deduplicated records
- `records_deduplicated.ris` — RIS export for Rayyan / ASReview
- `maybe_pairs.csv` — uncertain duplicate pairs flagged for human review (ASySD only)
- `prisma_search_metadata.json` — PRISMA flow diagram numbers
- `search_log.txt` — full execution log
- `manual_queries/` — ready-to-paste queries for WoS and PsycINFO (Ovid syntax)

The generated raw screening outputs are not committed by default; the committed benchmark fixtures and summaries are documented in [data/README.md](data/README.md).

## Methodology decisions

Documented in the [PROSPERO protocol](docs/prospero_protocol_neuroimaging.md). Key choices:

- **PECO framework:** Population = adults with FND; Exposure = having FND; Comparator = healthy controls; Outcome = convergent brain abnormalities via ALE
- **ALE inclusion:** studies must report MNI or Talairach coordinates; others enter narrative synthesis
- **Risk of bias:** Newcastle-Ottawa Scale + neuroimaging-specific quality supplement
- **Screening:** AI-assisted dual screening (LLM + human), validated against two independent gold standards
- **Deduplication:** ASySD-class algorithm (author + abstract similarity) as default
- **Citation chasing:** backward (reference lists) + forward (Google Scholar "Cited by")

## Validation

We validated both the search strategy and the LLM screening pipeline against two independent gold standards:

1. **Boeckle et al. (2016)** — 33/35 in-scope neuroimaging studies recovered by our search terms. The 16 unrecovered studies are out of scope (EEG/MEG/CT or non-FND diagnoses).
2. **Ludwig et al. (2018)** — 15/15 findable trauma/stressor studies correctly included by the LLM screener (100% sensitivity).

All validation materials (scripts, data, prompts, search runs, reports) are archived in [`validation/`](validation/README.md) with full reproduction instructions.

## References

- Boeckle M, Liegl G, Jank R, Pieh C (2016). Neural correlates of conversion disorder: overview and meta-analysis of neuroimaging studies on motor conversion disorder. *BMC Psychiatry*, 16, 195.
- Mavroudis I et al. (2024). A Voxel-Wise Meta-Analysis of the Volumetric Changes in Functional Neurological Disorders. *Iran J Psychiatry Behav Sci*, 18(4), e148266.
