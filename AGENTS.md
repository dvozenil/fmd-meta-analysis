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
| `prompts/neuroimaging_v1.txt` | Production screening prompt (Boeckle benchmark). |
| `prompts/trauma_v1.txt` | Ludwig cross-validation prompt. |
| `docs/repo_cleanup_and_next_steps.md` | Authoritative project status and roadmap. |
| `docs/methods_paper_plan.md` | Design for the model-comparison methods paper. |
| `data/validation_screening_set.jsonl` | 709 records, 25 gold-label includes (Boeckle benchmark). |
| `data/ludwig_included_studies.csv` | 34 gold-label studies (Ludwig benchmark). |

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
  JSON with decision, confidence, reason, exclusion_reason, and domain-specific
  tags. The JSON schema is embedded in the prompt itself.

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

## Current state (2026-06-10)

- **Boeckle validation complete:** 25/25 sensitivity, 50-record human
  comparison with 0 LLM misses. Qwen 3.5 122B is the validated model.
- **Ludwig cross-validation complete:** 14/14 = 100% sensitivity on held-out
  benchmark. Search run (`fnd_search_20260528_111459/`): 197 deduplicated
  records, 14/34 Ludwig studies matched (20 unfindable via title/abstract —
  terms only in full text). DOI resolver bugs fixed (4 collision errors).
- **Methods paper planned:** dual-benchmark model-ladder comparison
  (5 model classes x 3 prompts x 2 benchmarks). Design in
  `docs/methods_paper_plan.md`.

## What's next

1. **Run the Ludwig cross-validation end-to-end.** Steps:
   ```bash
   # Set up credentials
   export OPENAI_BASE_URL="https://llm.ai.e-infra.cz/v1"
   export OPENAI_API_KEY="$E_INFRA_API_TOKEN"

   # 1. Build validation JSONL (already done if fnd_search_20260528_111459 exists)
   python3 scripts/validate_ludwig_recall.py --search-dir fnd_search_20260528_111459

   # 2. Screen with Qwen 3.5 122B using trauma prompt
   OPENAI_MODEL=qwen3.5-122b python3 scripts/llm_screen_abstracts.py \
     --input data/ludwig_validation_set.jsonl \
     --output data/ludwig_screening_results.jsonl \
     --prompt prompts/trauma_v1.txt \
     --workers 4 --no-response-format --no-thinking

   # 3. Check sensitivity against gold labels
   python3 scripts/check_pilot_results.py data/ludwig_screening_results.jsonl \
     --gold data/ludwig_validation_set.jsonl
   ```
2. **Finalize and freeze search terms** for the production meta-analysis.
3. **Run the production search** (`--full`, no date cutoff) once terms are frozen.
4. **Methods paper model runs** (if pursued): add WMCC metrics, run model
   ladder, analyze per `docs/methods_paper_plan.md`.

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

## Testing

No formal test suite. Validation is done via:
- `scripts/validate_os_recall.py` — Boeckle sensitivity check
- `scripts/validate_ludwig_recall.py` — Ludwig sensitivity check
- `scripts/compare_human_llm.py` — inter-rater comparison
- `scripts/check_pilot_results.py --gold <file>` — quick accuracy on subsets

## External links

- GitHub: https://github.com/dvozenil/fmd-meta-analysis
- Notion project hub: https://app.notion.com/p/352cf8786b8180c0b2d4ecb65b85c14d
- Notion protocol: https://app.notion.com/p/352cf8786b81816fb261cff71e17249f
