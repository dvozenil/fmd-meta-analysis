# Reusing the Search Pipeline

This guide explains how to configure and run the FND meta-analysis search
pipeline for a new systematic review using YAML config files.

Introduced by [issue #8](https://github.com/dvozenil/fmd-meta-analysis/issues/8):
the fixed term lists that used to live inside `fnd_meta_search.py` are now
externalized into YAML config files under `search_configs/`, and a `--db` flag
lets you select which databases to query. The existing mode flags still work
exactly as before (see [Existing Modes](#existing-modes-backward-compatible)).

## Quick Start

1. Copy the template:
   ```bash
   cp search_configs/template.yaml my_project.yaml
   ```
2. Edit `my_project.yaml` with your search terms and options.
3. Run:
   ```bash
   python fnd_meta_search.py --terms my_project.yaml --auto
   ```

`--terms <path>` takes the path to any YAML config file. It **takes precedence
over** the `--mode` / `--update` / `--full` / ... flags, so you can point the
pipeline at your own config regardless of the built-in modes.

## YAML Config Schema

All keys are optional unless noted. Unset options fall back to the defaults in
`SearchConfig` (see `fnd_meta_search.py`).

### project

Metadata only — does not affect the query build.

- `name` — **REQUIRED** project identifier (short human label).
- `description` — human-readable description.
- `version` — config version string.

Example:
```yaml
project:
  name: "trauma-fnd-variant"
  description: "New systematic review: FND in trauma-exposed populations"
  version: "1.0"
```

### search

- `mode` — informational; one of the 5 existing modes (`update`, `full`,
  `os_validation`, `os_table_recall`, `ludwig_validation`) or `"custom"`.
  For a new review use `"custom"`.
- `date_start` — `"inception"` (equivalent to year 1800) or an integer year,
  e.g. `2015`.
- `date_end` — `"today"` or a `YYYY/MM/DD` date, e.g. `"2026/07/31"`.
- `language_filter` — `true` (restrict to English) or `false` (no language
  restriction). Applies to WoS, Europe PMC, Scopus, and EBSCO; PubMed's
  non-MeSH branch never adds a language filter.
- `syntax` — per-database overrides (see below).

### term_sets and blocks

- `term_sets` — **REQUIRED** named lists of search terms.
- `blocks` — **REQUIRED** maps `block_a` / `block_b` / `block_c` to term-set
  names. `block_a` and `block_b` are combined with **AND**; a `null` (or
  absent) `block_c` means a 2-block query (A AND B). For a 3-block AND query,
  set `block_c` to a third term-set (e.g. study-design terms).

Terms are quoted **verbatim** into every database syntax, so include any
truncation wildcards (`*`) exactly as they should be searched.

```yaml
term_sets:
  fnd_terms:                       # REQUIRED — block_a source
    - "functional neurological disorder*"
    - "conversion disorder*"
  imaging_terms:                   # REQUIRED — block_b source
    - "neuroimaging"
    - "brain imaging"
  design_terms:                    # optional 3rd block
    - "control"
    - "controlled"

blocks:
  block_a: "fnd_terms"             # REQUIRED — key into term_sets
  block_b: "imaging_terms"         # REQUIRED — key into term_sets
  block_c: null                    # optional 3rd block
```

### Exclusion blocks (NOT)

The YAML schema supports an optional **negated** block named `exclude` under
`blocks:`. When set, its terms are appended **AFTER all AND blocks** as a
per-database NOT clause. This is useful when you want to subtract a modality
already covered by another review (e.g. `"functional MRI"` / `"fMRI"`) or a
confounder disease (e.g. `"Huntington disease"`).

```yaml
term_sets:
  # ... block_a and block_b term_sets as above ...
  exclude_terms:
    - "functional MRI"
    - "fMRI"
    - "Huntington disease"

blocks:
  block_a: "fnd_terms"
  block_b: "imaging_terms"
  block_c: null
  exclude: "exclude_terms"   # optional; null or absent = no NOT clause
```

Per-database rendering of the example above:

| Database | Exclusion syntax |
|---|---|
| **PubMed** | ` NOT ("functional MRI"[tiab] OR "fMRI"[tiab] OR "Huntington disease"[tiab])` |
| **Web of Science** | ` AND NOT TS=("functional MRI" OR "fMRI" OR "Huntington disease")` |
| **Europe PMC** | ` NOT (TITLE_ABS:("functional MRI" OR "fMRI" OR "Huntington disease"))` |
| **Scopus** | ` AND NOT TITLE-ABS-KEY("functional MRI" OR "fMRI" OR "Huntington disease")` |
| **EBSCO / PsycINFO** | ` AND NOT (TI (...) OR AB (...) OR SU (...))` |

When `exclude` is unset (or `null`), queries are **byte-identical** to the
pre-exclusion behaviour — the golden regression tests enforce this.

### Per-database syntax overrides

Under `search.syntax` you can override options per database. Currently only
the PubMed block exposes options; the other databases have no per-DB
overrides. Each option is explained below.

```yaml
search:
  syntax:
    pubmed:
      use_mesh: true
      mesh_terms_fnd:
        - "Conversion Disorder"
        - "Dissociative Disorders"
      mesh_terms_imaging:
        - "Neuroimaging"
        - "Magnetic Resonance Imaging"
      use_exclusions: true
      use_human_filter: true
    mri_fallback: false
```

Option reference:

- `pubmed.use_mesh` — `true` wraps the text blocks in MeSH descriptors
  (production default); `false` produces a plain `[tiab]` text-block query
  (used by the validation modes).
- `pubmed.mesh_terms_fnd` — MeSH heading(s) OR'd ahead of the FND text block
  (e.g. `Conversion Disorder`, `Dissociative Disorders`).
- `pubmed.mesh_terms_imaging` — MeSH heading(s) OR'd ahead of the imaging text
  block (e.g. `Neuroimaging`, `Magnetic Resonance Imaging`,
  `Diffusion Tensor Imaging`, `Positron-Emission Tomography`, etc.).
- `pubmed.use_exclusions` — `true` adds `NOT (Editorial OR Letter OR Comment)`.
- `pubmed.use_human_filter` — `true` adds `("humans"[MeSH Terms])`.
- `mri_fallback` — `true` adds `OR ("magnetic" AND "resonance" AND "imaging")`
  to the imaging block in **every** database. This is a Boeckle
  `os_validation` quirk; default is `false`.

The language filter is a **single global flag**: top-level `search.language_filter`
applies to every database — there is no per-database language override. Set it
to `true` to restrict to English, or `false` for no language restriction.

## Using --db to Select Databases

The `--db` flag (repeatable) restricts which API clients actually **execute**.
All five query strings are still generated and written to `queries.json` /
`queries.txt` regardless of `--db`, so the reproducible query artifact is
always complete.

```bash
# Run only PubMed and EuropePMC
python fnd_meta_search.py --terms my_project.yaml --db pubmed --db europepmc --no-dedup
```

Valid `--db` values: `pubmed`, `europepmc`, `wos`, `scopus`.
Note: the `ebsco_psycinfo` query is **always generated** but never
auto-executed (PsycINFO has no REST API — it is searched manually via
EBSCOhost and imported in the dedup phase).

## Existing Modes (Backward Compatible)

The 5 existing mode flags still work and are now thin wrappers that load the
corresponding YAML file from `search_configs/`:

| Flag | Loads |
|---|---|
| `--update` | `search_configs/update.yaml` |
| `--full` | `search_configs/full.yaml` |
| `--os_validation` | `search_configs/os_validation.yaml` |
| `--os_table_recall` | `search_configs/os_table_recall.yaml` |
| `--ludwig_validation` | `search_configs/ludwig_validation.yaml` |

Because the mode flags now load YAML, you can inspect each mode's exact term
lists by reading its file under `search_configs/`.

## Adding a New Database Client

To wire a brand-new API database into the pipeline:

1. Create a new client class with a `.search(query) -> list[Record]` method
   (mirror the existing `PubMedClient`, `EuropePMCClient`, etc.).
2. Add it to the `clients` dict in `run_searches()` (the `clients: dict[str,
   tuple]` block that maps each DB name to `(Client(), query)`).
3. Add the db name to the `--db` parser `choices` in `_parse_args()` and to its
   help text.
4. Add golden query generation for the new db — a `build_<db>_query(config)`
   function, plus a golden entry in each `tests/golden/<mode>/queries.json`.

If your new database has no free REST API (like EBSCO PsycINFO), it can still
have a generated query in `queries.json` for manual execution, without being an
auto-run client.

## Golden Query Regression Tests

The test suite in `tests/test_golden_queries.py` is the **safety net** for this
refactor. For each of the 5 modes and each of the 5 databases (including
`ebsco_psycinfo`), it reloads the mode's YAML config, rebuilds the query, and
asserts it matches the frozen golden reference byte-for-byte.

The golden files live under `tests/golden/<mode>/queries.json` and were
generated from the **pre-refactor** code as the byte-identical contract. The
set of golden files is immutable: if you change query output, the tests will
fail — and the golden files are **not** meant to be edited just to turn the
tests green.

Update the golden files **only** when you are *intentionally* changing a
query's output (a deliberate term/date/syntax change you have decided on), never
to hide a regression. To regenerate them, rerun the query builders against the
new config and update the corresponding `tests/golden/<mode>/queries.json`.

Run the suite with:
```bash
python -m pytest tests/ -q
```

## Example: New Review Project

Concrete walk-through for a new review (e.g. a trauma/FND variant search):

1. **Copy the template:**
   ```bash
   cp search_configs/template.yaml trauma_fnd.yaml
   ```
2. **Fill in the terms.** Replace `fnd_terms` / `imaging_terms` (and optionally
   add a `design_terms` third block) with your review's terms. Keep any `*`
   truncation wildcards.
3. **Set the date range.** Pick `date_start` (`"inception"` or a year) and
   `date_end` (`"today"` or a specific date) for your review window.
4. **Choose the language filter.** Set `language_filter: true` to restrict to
   English, or `false` for no restriction. This single global flag applies to
   every database — there is no per-database override.
5. **Test on one database first** to validate the query shape and hit count
   before spending API quota on all sources:
   ```bash
   python fnd_meta_search.py --terms trauma_fnd.yaml --db pubmed --no-dedup --auto
   ```
   Inspect the generated `queries.json` / `queries.txt` to confirm the Boolean
   strings look sane.
6. **Run the full search** across all databases:
   ```bash
   python fnd_meta_search.py --terms trauma_fnd.yaml --auto
   ```
   (Add `--no-dedup` and a later `--dedup <dir>` pass if you have manual
   exports such as PsycINFO/EBSCOhost to fold in, per the two-phase workflow in
   the [README](../README.md).)
