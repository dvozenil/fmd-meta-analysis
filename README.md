# FND Neuroimaging Meta-Analysis

Updated and extended meta-analysis of neuroimaging findings in Functional Neurological Disorder (FND), building on [Boeckle et al. (2016)](https://doi.org/10.1186/s12888-016-0890-x).

## Project overview

| | |
|---|---|
| **PI** | Petr Sojka |
| **Student lead** | David Voženílek |
| **Notion workspace** | [Project hub](https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d) · [Protocol](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f) |
| **Status** | Planning / search strategy development |

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
fnd_meta_search.py      # PRISMA-compliant API search script
requirements.txt        # Python dependencies
s12888-016-0890-x.pdf   # Boeckle et al. (2016) — original study
A_Voxel-Wise_Meta-...   # Mavroudis et al. (2024) — existing structural meta-analysis
```

## Search script

`fnd_meta_search.py` queries PubMed, Europe PMC, Web of Science, and Scopus via their APIs. PsycINFO is searched manually (no REST API).

### Two search modes

```bash
# Functional track: 2015 onward (updating the original study)
FND_SEARCH_MODE=update python fnd_meta_search.py

# Structural track: inception to present (no prior comprehensive ALE)
FND_SEARCH_MODE=full python fnd_meta_search.py
```

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Required: NCBI email (free account)
export NCBI_EMAIL="your.email@institution.edu"

# Recommended: NCBI API key (10 req/s vs 3/s — free at ncbi.nlm.nih.gov/account/settings)
export NCBI_API_KEY="your_key"

# Optional: institutional API keys (script skips gracefully if missing)
export WOS_API_KEY="your_key"
export SCOPUS_API_KEY="your_key"
```

### Output

Each run creates a timestamped folder (`fnd_search_YYYYMMDD_HHMMSS/`) containing:

- `queries.json` — exact Boolean strings used (reproducibility anchor)
- `raw_<database>.csv` — per-database results before dedup
- `records_deduplicated.csv` — unified deduplicated records
- `records_deduplicated.ris` — RIS export for Rayyan / ASReview
- `prisma_search_metadata.json` — PRISMA flow diagram numbers
- `search_log.txt` — full execution log

## Methodology decisions

Documented in the [Notion protocol page](https://app.notion.com/p/352cf8786b81816fb261cff71e17249f). Key choices:

- **ALE inclusion:** studies must report MNI or Talairach coordinates; others enter narrative synthesis
- **Risk of bias:** Newcastle-Ottawa Scale + neuroimaging-specific quality supplement
- **Screening:** AI-assisted dual screening (LLM + human), validated against original study results
- **Citation chasing:** backward (reference lists) + forward (Google Scholar "Cited by")

## References

- Boeckle M, Liegl G, Jank R, Pieh C (2016). Neural correlates of conversion disorder: overview and meta-analysis of neuroimaging studies on motor conversion disorder. *BMC Psychiatry*, 16, 195.
- Mavroudis I et al. (2024). A Voxel-Wise Meta-Analysis of the Volumetric Changes in Functional Neurological Disorders. *Iran J Psychiatry Behav Sci*, 18(4), e148266.
