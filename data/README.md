# Data

This directory holds production data for the meta-analysis pipeline.

Validation data (gold-standard CSVs, benchmark JSONLs, screening results,
pilot outputs) has been moved to `validation/data/`. See
`validation/README.md` for the full reproduction archive.

## What goes here (production)

- Search run outputs are generated into timestamped `fnd_search_*/`
  directories at the repo root (gitignored).
- Production screening outputs will go here once the production search
  is finalized.
