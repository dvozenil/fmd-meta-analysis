# Data

This directory holds the small benchmark fixtures and evaluation outputs that
support the LLM screening work.

Tracked fixtures:

- `test_abstracts_20.jsonl`
- `test_abstracts_20_protocol_resolved.jsonl`
- `test_abstracts_20_protocol_resolved.csv`

Tracked evaluation outputs:

- `evaluation_summary_*.csv`
- `evaluation_disagreements_*.jsonl`

Generated raw model outputs (`llm_screening_results_*.jsonl`) and ad hoc old
result files are intentionally ignored and can be regenerated from the scripts
in `scripts/`.
