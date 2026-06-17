# FND Neuroimaging Meta-Analysis

Updated and extended meta-analysis of neuroimaging findings in Functional Neurological Disorder (FND), building on [Boeckle et al. (2016)](https://doi.org/10.1186/s12888-016-0890-x).

## Project overview

| | |
|---|---|
| **PI** | Petr Sojka |
| **Student lead** | David Voženílek |
| **Notion workspace** | [Project hub](https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d) · [Protocol](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f) |
| **Status** | Search validation / LLM screening pipeline |

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
fnd_meta_search.py          # PRISMA-compliant API search script (PubMed, Europe PMC, WoS, Scopus)
requirements.txt            # Python dependencies
prompts/
  neuroimaging_v1.txt       # Production neuroimaging screening prompt
scripts/
  llm_screen_abstracts.py   # LLM title/abstract screening (OpenAI-compatible)
docs/
  repo_cleanup_and_next_steps.md   # Current status and roadmap
  methods_paper_plan.md            # Model-comparison methods paper design
  llm_screening_protocol.md       # Screening execution protocol
  references/                      # Literature reviews and source PDFs
validation/                        # Self-contained validation archive
  README.md                        # Full reproduction instructions
  scripts/                         # Frozen scripts (search, screener, validators)
  data/                            # Gold standards, screening results, pilots
  prompts/                         # Prompts used (neuroimaging + trauma)
  search_runs/                     # Archived search outputs (Boeckle + Ludwig)
  docs/                            # Validation reports
```

Source PDFs are kept locally in [docs/references/](docs/references/README.md) and are not versioned.

## Search script

`fnd_meta_search.py` queries PubMed, Europe PMC, Web of Science, and Scopus via their APIs. PsycINFO is searched manually (no REST API).

IMPORTANT: Institutional VPN must be connected for Scopus API to retrieve abstracts.

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
```

The `os_table_recall` mode exists as a reference for how we attempted to
replicate the OS search and why exact replication is not viable. See
[docs/os_validation_report.md](docs/os_validation_report.md) for details.

The `ludwig_validation` mode implements the Ludwig et al. (2018) search
strategy (FND x stressor x study-design, inception to Nov 2016) for
independent cross-validation of the LLM screening pipeline.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Put API keys in .env at the repo root. Start from:
cp .env.example .env
```

The search script loads `.env` automatically. Missing Scopus/WoS keys are handled
gracefully; those databases are skipped and logged.

### Output

Each run creates a timestamped folder (`fnd_search_YYYYMMDD_HHMMSS/`) containing:

- `queries.json` — exact Boolean strings used (reproducibility anchor)
- `raw_<database>.csv` — per-database results before dedup
- `records_deduplicated.csv` — unified deduplicated records
- `records_deduplicated.ris` — RIS export for Rayyan / ASReview
- `prisma_search_metadata.json` — PRISMA flow diagram numbers
- `search_log.txt` — full execution log

The generated raw screening outputs are not committed by default; the committed
benchmark fixtures and summaries are documented in [data/README.md](data/README.md).

## Methodology decisions

Documented in the [Notion protocol page](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f). Key choices:

- **ALE inclusion:** studies must report MNI or Talairach coordinates; others enter narrative synthesis
- **Risk of bias:** Newcastle-Ottawa Scale + neuroimaging-specific quality supplement
- **Screening:** AI-assisted dual screening (LLM + human), validated against original study results
- **Citation chasing:** backward (reference lists) + forward (Google Scholar "Cited by")

## Search validation

We validated our search strategy by running the `full` production terms with the
OS cutoff date (inception to 2015/08/31) and cross-referencing against the 49
studies in Boeckle et al. Table 1. Result: **33/35 in-scope studies recovered**.
The 16 unrecovered studies are all out of scope (EEG/MEG/CT imaging or non-FND
diagnoses like body dysmorphic disorder). See
[docs/os_validation_report.md](docs/os_validation_report.md) for the full
analysis.

The validation set (`data/validation_screening_set.jsonl`) has the 33 matched
OS studies pre-labeled as `include_candidate` for LLM pipeline sensitivity
testing.

For the current working state, see [docs/repo_cleanup_and_next_steps.md](docs/repo_cleanup_and_next_steps.md).

## References

- Boeckle M, Liegl G, Jank R, Pieh C (2016). Neural correlates of conversion disorder: overview and meta-analysis of neuroimaging studies on motor conversion disorder. *BMC Psychiatry*, 16, 195.
- Mavroudis I et al. (2024). A Voxel-Wise Meta-Analysis of the Volumetric Changes in Functional Neurological Disorders. *Iran J Psychiatry Behav Sci*, 18(4), e148266.
