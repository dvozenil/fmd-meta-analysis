# FND Neuroimaging Meta-Analysis

Updated and extended meta-analysis of neuroimaging findings in Functional Neurological Disorder (FND), building on [Boeckle et al. (2016)](https://doi.org/10.1186/s12888-016-0890-x).

## Project overview

| | |
|---|---|
| **PI** | Petr Sojka |
| **Student lead** | David Voženílek |
| **GitHub** | [dvozenil/fmd-meta-analysis](https://github.com/dvozenil/fmd-meta-analysis) |
| **Notion** | [Project hub](https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d) · [Protocol](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f) |
| **Status** | Pipeline v2 — DOI fix + abstract recovery integrated |

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

`fnd_meta_search.py` queries PubMed, Europe PMC, Web of Science, and Scopus via their APIs. PsycINFO has no REST API and is searched manually via EBSCOhost. The script supports a **two-phase workflow**: run all searches first, collect manual exports, then deduplicate everything at once.

### Quick start

```bash
# Phase 1: Run searches (API databases only, no dedup)
python fnd_meta_search.py --full --no-dedup

# (human: run EBSCOhost PsycINFO query from queries.txt, drop CSV into output dir)
# (human: run WoS query from queries.txt if API unavailable, drop RIS into output dir)

# Phase 2: Deduplicate all sources and export final PRISMA artifacts
python fnd_meta_search.py --dedup fnd_search_YYYYMMDD_HHMMSS/

# Or run everything in one pass (API databases only, no manual imports)
python fnd_meta_search.py --full
```

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
python fnd_meta_search.py --full --dedup-algo simple   # DOI + title-hash only
python fnd_meta_search.py --full --dedup-algo asysd    # ASySD-class (default)
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

### Scopus enrichment

The Scopus search API returns bibliographic metadata (title, DOI, year, journal) but only the first author (`dc:creator`). When using the COMPLETE search view, abstracts (`dc:description`) are included for ~88% of records. The script enriches the remaining records via the Elsevier Abstract Retrieval API, which also fills in the **full author list** needed for dedup matching.

### Cross-database abstract recovery

After all databases are fetched (and Scopus enrichment is done), the pipeline runs a cross-database abstract recovery pass for any records still missing abstracts:

1. **PubMed efetch by PMID** — for PubMed records that came back without an abstract
2. **PubMed title search → efetch** — for non-PubMed records (Scopus, WoS, PsycInfo, EuropePMC) whose title can be found in PubMed
3. **EuropePMC title search** — broader coverage including conference papers

This runs **before** deduplication so the similarity matcher has maximum text. Typical recovery rate: ~20% of empty abstracts recovered.

### Deduplication

Two algorithms are available via `--dedup-algo`:

- **ASySD-class** (default): Uses `rapidfuzz` fuzzy string matching on author lists and abstracts to detect duplicates across databases, plus DOI matching. Handles cross-database duplicates (e.g., PubMed/Scopus overlap) that simple DOI matching misses when DOIs are absent.
- **Simple**: DOI-normalized match + title+year hash. Faster but misses records without DOIs or with variant titles.

### Two-phase workflow

When manual database exports are involved (PsycINFO via EBSCOhost, or WoS when API is unavailable), use the split workflow:

```bash
# Phase 1: Search only — save raw CSVs and manual queries
python fnd_meta_search.py --full --no-dedup

# (Add EBSCOhost CSV exports and/or WoS RIS exports to the output directory)

# Phase 2: Dedup all sources and export final artifacts
python fnd_meta_search.py --dedup fnd_search_YYYYMMDD_HHMMSS/
```

The dedup phase auto-discovers all sources in the directory:
- `raw_*.csv` — API exports (Record schema)
- `EBSCO*.csv` — EBSCOhost exports (PsycINFO / PsycArticles format)
- `*.ris` — RIS files (WoS or other manual exports)

Multiple RIS files from the same database are automatically combined. The dedup can be re-run safely — it skips manual export files when their corresponding `raw_<db>.csv` already has data.

### Output

Each run creates a timestamped folder (`fnd_search_YYYYMMDD_HHMMSS/`) containing:

- `queries.json` — exact Boolean strings used (reproducibility anchor)
- `queries.txt` — human-readable query file for copy-paste into manual databases
- `raw_<database>.csv` — per-database results before dedup (includes manual imports after dedup phase)
- `records_deduplicated.csv` — unified deduplicated records
- `records_deduplicated.ris` — RIS export for Rayyan / ASReview / Covidence / EndNote
- `maybe_pairs.csv` — uncertain duplicate pairs flagged for human review (ASySD only)
- `prisma_search_metadata.json` — PRISMA flow diagram numbers
- `search_log.txt` — full execution log

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
