# AGENTS.md

## Project

FND Neuroimaging Meta-Analysis — an updated and extended ALE meta-analysis
of neuroimaging in Functional Neurological Disorder, building on
Boeckle et al. (2016). Includes an LLM-assisted screening pipeline and
validation infrastructure.

PI: Petr Sojka. Student lead: David Voženílek.

## Key files

| Path | Purpose |
|------|---------|
| `fnd_meta_search.py` | Main search script (PubMed, Europe PMC, WoS, Scopus). Two-phase workflow: `--no-dedup` for search-only, `--dedup DIR` for dedup-only. Imports EBSCO CSV and RIS manual exports. |
| `dedup_asysd.py` | ASySD-class deduplication algorithm (Python port of R ASySD). |
| `scripts/llm_screen_abstracts.py` | LLM screening pipeline (OpenAI-compatible). Supports `--prompt`, `--thinking`, `--no-thinking`. |
| `prompts/neuroimaging_v1.txt` | Production screening prompt. |
| `docs/repo_cleanup_and_next_steps.md` | Authoritative project status and roadmap. |
| `docs/methods_paper_plan.md` | Design for the model-comparison methods paper. |
| `validation/` | Self-contained validation archive (scripts, data, prompts, search runs, reports). |
| `validation/README.md` | Full reproduction instructions for both benchmarks. |

## Architecture

- **Search** is entirely in `fnd_meta_search.py`. Modes (`--update`, `--full`,
  `--os_validation`, `--os_table_recall`, `--ludwig_validation`) control term
  sets and date ranges. Add `--auto` to skip interactive prompts.

  **Two-phase workflow:** Use `--no-dedup` to run searches only (saves raw CSVs
  + queries for manual databases). After adding EBSCOhost CSV exports and/or
  WoS RIS exports to the output directory, run `--dedup <dir>` to import
  everything, deduplicate, and export final PRISMA artifacts. The dedup phase
  auto-discovers `raw_*.csv`, `EBSCO*.csv`, and `*.ris` files.

  **Dedup algorithm:** `--dedup-algo asysd` (default, ASySD-class) or
  `--dedup-algo simple` (DOI+title hash). ASySD uses Jaro-Winkler similarity
  on authors, titles, abstracts, and bibliographic fields.
- **Screening** is in `scripts/llm_screen_abstracts.py`. It calls any
  OpenAI-compatible endpoint (LM Studio for local models, API for frontier).
  System prompt is loaded from `--prompt <file>` or falls back to the embedded
  default. Output is JSONL with one JSON object per record.
- **Validation scripts** (`scripts/validate_os_recall.py`,
  `scripts/validate_ludwig_recall.py`) cross-reference search results against
  gold-standard study lists using DOI-first matching with title fallback.
- **Prompts** live in `prompts/` as plain text files. They return structured
  JSON with decision, confidence, reason, exclusion_reason, domain-specific
  tags, and criteria-ID arrays (`inclusion_criteria_applied`,
  `exclusion_criteria_applied`). Each inclusion/exclusion criterion has a
  stable ID (I1–I3, E1–E5/E7) for traceability. The JSON schema is embedded
  in the prompt itself.

## Conventions

- Python 3.11+. Dependencies in `requirements.txt`.
- API keys go in `.env` (see `.env.example`). Never commit `.env`.
- **Primary LLM endpoint:** e-INFRA MetaCentrum at
  `https://llm.ai.e-infra.cz/v1` (token-authenticated, OpenAI-compatible).
  Model name on this endpoint: `qwen3.5-122b`. Use `--no-response-format`
  and `--no-thinking` for screening runs (the endpoint doesn't support
  `response_format=json_object` and thinking-off gives validated results).
- Generated search runs land in timestamped `fnd_search_*/` directories
  (gitignored). Committed data lives in `data/`.
- Gold-label categories: `include_candidate` (strict, must recover) and
  `include_broad_scope` (counted separately, not against sensitivity).
- All scripts use `argparse` and are runnable from the repo root.
- Screening model output must be valid JSON matching the schema in the prompt.
  Parse failures are treated as "include" (safe default).

## Current state (2026-07-17)

- **Production search complete:** `fnd_search_20260717_123354/` — 5 databases,
  7,058 raw records, 3,530 unique after ASySD dedup. PsycINFO (EBSCOhost,
  485 records) and WoS (3× RIS export due to 1,000-record limit, 2,055
  records) imported manually. Scopus search switched to POST to handle
  expanded query terms (413 Payload Too Large on GET).
- **500 maybe-pairs** flagged for manual review (7.5% of pairs); 120 share
  the same DOI (definite duplicates). Most are WoS RIS formatting artifacts
  (hyphenated compound terms reducing Jaro-Winkler title similarity).
- **529 records (15%) missing abstracts:** 251 Scopus (pre-1996 records),
  242 WoS (export limitations), 32 PubMed, 4 Europe PMC. Reported in
  `prisma_search_metadata.json` under `abstracts_missing`. Screen by title;
  retrieve full text where title is insufficient.
- **Boeckle validation complete:** 25/25 sensitivity.
- **Ludwig cross-validation complete:** 15/15 = 100% sensitivity.
- **Criteria-ID traceability** and thread-safe output implemented.
- **Methods paper planned:** design in `docs/methods_paper_plan.md`.

## What's next

1. **Resolve maybe-pairs** — batch-merge 120 same-DOI pairs, scan remaining ~380.
2. **Begin title/abstract screening** — human + LLM dual screening on the
   3,530 deduplicated records.
3. **Handle missing abstracts** — screen by title; retrieve full text for
   ambiguous cases.
4. **Methods paper model runs** (if pursued): add WMCC metrics, run model
   ladder, analyze per `docs/methods_paper_plan.md`.

## Validation archive

All validation data, scripts, prompts, search runs, and results are
archived in `validation/` as a self-contained reproduction package.
See `validation/README.md` for full instructions. Two git tags mark the
validation milestones:

- `v0.1-validation-complete` — original 40/40 validation; the frozen
  archive matches this state.
- `v0.2-criteria-ids` — criteria-ID revalidation (I1–I3, E1–E5/E7
  traceability), 40/40 sensitivity maintained. Reproducing this requires
  the **root** `scripts/llm_screen_abstracts.py` + the
  `validation/prompts/` prompts (the frozen archive screener is the
  pre-criteria-ID `v0.1` version).

## Gotchas

- Scopus search uses POST (not GET) to avoid 413 Payload Too Large with
  the expanded search terms. The `_probe_search_view` method still uses
  GET for the tiny probe query.
- Scopus abstracts may be missing for pre-1996 records — these are
  genuinely absent from the database, not an enrichment failure.
- WoS RIS exports use hyphens in compound terms ("MAGNETIC-RESONANCE"),
  which after ASySD punctuation stripping produce concatenated words
  ("MAGNETICRESONANCE") that reduce title similarity. Our pre-processing
  normalizes hyphens to spaces before dedup, but some edge cases remain.
- WoS only allows 1,000 records per RIS export; split into multiple files
  (`wos_1.ris`, `wos_2.ris`, etc.). The dedup phase auto-combines them.
- Scopus abstracts require institutional VPN. The script handles missing
  Scopus gracefully (logs and skips).
- `--os_table_recall` mode is reference-only — it demonstrates why exact OS
  replication isn't viable. Don't use it for production.
- The Ludwig search uses a 3-block AND (FND x stressor x design); this is
  handled internally by `SearchTermConfig` in `fnd_meta_search.py`.
- When adding new search modes: update `VALID_SEARCH_MODES`,
  `_VALIDATION_MODES`, `_VALIDATION_END_DATES`, and `_active_term_config()`.
- LM Studio sometimes rejects `response_format=json_object`; use
  `--no-response-format` in that case.
- Prompt JSON schemas define the allowed enum values for tags. If you change
  the schema, update both the prompt file and `ALLOWED_VALUES` in the screener.
- When adding or renaming criteria, update the IDs in the prompt file and
  re-verify that the screener's `normalize_and_validate_decision()` handles
  the new arrays correctly.

## Testing

No formal test suite. Validation is done via:
- `validation/scripts/validate_os_recall.py` — Boeckle sensitivity check
- `validation/scripts/validate_ludwig_recall.py` — Ludwig sensitivity check
- `validation/scripts/compare_human_llm.py` — inter-rater comparison
- `validation/scripts/check_pilot_results.py --gold <file>` — quick accuracy on subsets

## External links

- GitHub: https://github.com/dvozenil/fmd-meta-analysis
- Notion project hub: https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d
- Notion protocol: https://app.notion.com/p/352cf8786b81816fb261cff71e17249f
