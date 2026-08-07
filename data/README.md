# Data

This directory holds production data for the meta-analysis pipeline.

Validation data (gold-standard CSVs, benchmark JSONLs, screening results,
pilot outputs) has been moved to `validation/data/`. See
`validation/README.md` for the full reproduction archive.

## What goes here (production)

- Search run outputs are generated into timestamped `fnd_search_*/`
  directories at the repo root (gitignored).
- **Production screening corpus (2026-07-31 search): `screening_corpus_2026-07-31/`** —
  raw exports, queries, PRISMA metadata, and the adjudicated final screening corpus
  (`records_deduplicated_adjudicated.ris`, 3,472 records). See its `README.md`.
