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
| `fnd_meta_search.py` | Main search script (PubMed, Europe PMC, WoS, Scopus). All search modes live here. |
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

## Current state (2026-06-17)

- **Boeckle validation complete:** 25/25 sensitivity, 50-record human
  comparison with 0 LLM misses. Qwen 3.5 122B is the validated model.
- **Ludwig cross-validation complete:** 15/15 = 100% sensitivity on held-out
  benchmark. Search run (`fnd_search_20260528_111459/`): 197 deduplicated
  records, 15/34 Ludwig studies matched (19 unfindable via title/abstract —
  terms only in full text). DOI resolver rewritten to use CrossRef key-based
  lookup (original had 7 collision errors from positional indexing).
- **Criteria-ID traceability added:** Prompts now label each
  inclusion/exclusion criterion with stable IDs (I1–I3, E1–E5/E7).
  Screening output includes `inclusion_criteria_applied` and
  `exclusion_criteria_applied` arrays. Revalidated on both benchmarks
  with identical 40/40 sensitivity. Results in
  `validation/data/criteria_ids/`.
- **Thread-safe output:** `append_jsonl` now uses `threading.Lock` for
  safe parallel writes.
- **Methods paper planned:** dual-benchmark model-ladder comparison
  (5 model classes x 3 prompts x 2 benchmarks). Design in
  `docs/methods_paper_plan.md`.

## What's next

1. **Finalize and freeze search terms** for the production meta-analysis.
2. **Run the production search** (`--full`, no date cutoff) once terms are frozen.
3. **Methods paper model runs** (if pursued): add WMCC metrics, run model
   ladder, analyze per `docs/methods_paper_plan.md`.

## Validation archive

All validation data, scripts, prompts, search runs, and results are
archived in `validation/` as a self-contained reproduction package.
See `validation/README.md` for full instructions. The git tag
`v0.1-validation-complete` marks the exact repo state.

## Gotchas

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
