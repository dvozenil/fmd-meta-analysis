# FND Meta-Analysis — Screening Corpus (2026-07-31 search)

This folder is the transparency/PRISMA record for the FND/functional-neurological-disorder
search of **2026-07-31** (cut-off `inception → 2026/07/31`) and the deduplication that
produced the screening corpus. It contains the raw database exports, the automated and
manual search queries, the PRISMA metadata, the deduplicated corpus, and the adjudicated
final screening set. `records_deduplicated_adjudicated.ris` is the file to import into
Rayyan / ASReview / Covidence for title/abstract screening.

**Run identity:** search 2026-07-31; dedup re-run 2026-08-05 with the
erratum/corrigendum fix. The search *method* is reproducible, not byte-identical (live
APIs drift; records indexed after the cut-off will differ on a fresh run).

## 1. Search metadata

| Field | Value |
|-------|-------|
| Search date | 2026-07-31 |
| Cut-off / search range | Inception → 2026/07/31 (`prisma_search_metadata.json`) |
| Profile | Expanded FND neuroimaging protocol (`search_mode=full`) |
| Databases | PubMed (1,207), Scopus (2,503), Web of Science (2,065), Europe PMC (825), PsycINFO/EBSCO (488) |
| Automated queries | `queries.json` / `queries.txt` |
| Manual search files | `EBSCO-Metadata-31. 07. 2026.csv` (PsycINFO, EBSCOhost), `savedrecs-*.ris` (WoS) |
| Search-stage filters | English; Humans (PubMed only — others at screening); excluded pub types: Editorial, Letter, Comment |

## 2. File manifest

| File | Purpose |
|------|---------|
| `queries.json`, `queries.txt` | Search queries — automated **and manual** (PsycINFO EBSCO) |
| `raw_pubmed.csv`, `raw_scopus.csv`, `raw_wos.csv`, `raw_europepmc.csv`, `raw_psycinfo.csv` | Raw per-database exports as used for dedup (see regeneration note) |
| `EBSCO-Metadata-31. 07. 2026.csv` | PsycINFO raw metadata (EBSCOhost) |
| `savedrecs-*.ris` | WoS manual (3-part) exports |
| `records_deduplicated_adjudicated.csv` / `.ris` | **Final screening corpus (3,472)** |
| `maybe_pairs_adjudicated.csv` | The 123 uncertain-duplicate pairs + how each was resolved |
| `doi_title_conflicts.csv` | Same-DOI pairs kept apart (erratum / language / abridgment) (7) |
| `adjudication_decision_log.md` | Full audit trail: exclusions, merges, keep-both decisions |
| `prisma_search_metadata.json` | PRISMA arithmetic + run metadata |

## 3. Deduplication & adjudication

- **Method:** ASySD-class Python port (`dedup_asysd.py`) + exact-DOI pre-collapse
  (`fnd_meta_search.py`), with **erratum/corrigendum/retraction title detection**
  (commit `ca5adc4`, branch `pipeline-v2-doi-fix-abstract-recovery`).
- **Result:** 7,088 raw → 3,562 unique → **3,472 final** after adjudication.
- **Adjudication:** the 123 maybe-pairs + conflicts were reviewed by the first author.
  Some duplicate pairs were **checked and merged manually**; erratum↔original pairs and
  other distinct records were kept apart. The rationale for every pair is in
  `adjudication_decision_log.md`; the decisions themselves are in
  `maybe_pairs_adjudicated.csv`.
- **Flow (PRISMA):**
  - 42 WoS `GRANTS:` funding records removed before screening (non-publications;
    "records removed before screening — other reasons")
  - 2 records excluded: RETRACTED article `10.1155/2022/8279357` + its retraction notice
  - 46 records merged-away across 42 duplicate components
  - Erratum↔original pairs kept separate (original screenable); errata screen as normal

## 4. Reproducibility

**Deduplication — exact (deterministic).** Re-running dedup on these raw files with the
pinned commit reproduces the 3,562 corpus:

```bash
python fnd_meta_search.py --dedup . --skip-abstract-recovery
```

**Search — method-reproducible, not byte-identical.** Re-running `--full` with the same
queries + cut-off `2026/07/31` reproduces the method, not identical bytes. The exact raw
files used are archived here.

> **Regeneration note:** `raw_pubmed.csv` and `raw_europepmc.csv` were re-fetched
> 2026-08-02 from their source APIs to repair HTML-in-title / title truncation
> (downstream of a parser fix; originals archived separately). All other raw files are
> the original 2026-07-31 exports.
