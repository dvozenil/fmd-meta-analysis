# Model comparison – pilot run (50 records)

Pilot subset: `data/validation_screening_set_50.jsonl`  
50 records, 15 confirmed `include_candidate`, 35 unlabelled (mix of exclusions and unknowns).  
Full validation set: `data/validation_screening_set.jsonl` (709 records).

---

## Prerequisites

```bash
export E_INFRA_API_TOKEN="<your token>"
export OPENAI_BASE_URL="https://llm.ai.e-infra.cz/v1"
export OPENAI_API_KEY="$E_INFRA_API_TOKEN"
```

---

## Thinking flag behaviour

The script sends `chat_template_kwargs: {thinking, enable_thinking}` to cover both
naming conventions used by different model families on the e-INFRA endpoint.

| CLI flag      | `chat_template_kwargs` sent            | Use for                              |
|---------------|----------------------------------------|--------------------------------------|
| *(omitted)*   | nothing (server default)               | models with no hybrid mode           |
| `--thinking`  | `thinking: true, enable_thinking: true` | force reasoning ON                  |
| `--no-thinking` | `thinking: false, enable_thinking: false` | force reasoning OFF              |

---

## Runs

Each run writes to its own output file so results are never mixed.
`--workers 4` is a safe starting point; raise to 8 if throughput is fine.

### Gemma 4 (31B dense) — primary candidate

```bash
# Default / no explicit thinking flag (Gemma doesn't advertise hybrid mode)
OPENAI_MODEL=gemma4 python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/gemma4_default.jsonl \
  --workers 4 --no-response-format

# Force thinking ON
OPENAI_MODEL=gemma4 python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/gemma4_thinking_on.jsonl \
  --workers 4 --no-response-format --thinking

# Force thinking OFF
OPENAI_MODEL=gemma4 python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/gemma4_thinking_off.jsonl \
  --workers 4 --no-response-format --no-thinking
```

### Qwen 3.5 122B — second candidate

```bash
OPENAI_MODEL=qwen3.5-122b python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/qwen3_5_122b_default.jsonl \
  --workers 4 --no-response-format

OPENAI_MODEL=qwen3.5-122b python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/qwen3_5_122b_thinking_on.jsonl \
  --workers 4 --no-response-format --thinking

OPENAI_MODEL=qwen3.5-122b python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/qwen3_5_122b_thinking_off.jsonl \
  --workers 4 --no-response-format --no-thinking
```

### Mistral Medium 3.5

```bash
OPENAI_MODEL=mistral-medium-3.5 python scripts/llm_screen_abstracts.py \
  --input  data/validation_screening_set_50.jsonl \
  --output data/pilot/mistral_medium_3_5_default.jsonl \
  --workers 4 --no-response-format
```

---

## Quick accuracy check after each run

```bash
# single file
python scripts/check_pilot_results.py data/pilot/gemma4_default.jsonl

# all pilot files at once
python scripts/check_pilot_results.py data/pilot/*.jsonl
```

---

## Notes

- `--no-response-format` is recommended for the e-INFRA endpoint; the script
  auto-drops the header on a 400 error too, but it saves a round-trip.
- If a model rejects `chat_template_kwargs` entirely, remove `--thinking` /
  `--no-thinking`; the key simply won't be sent.
- Once a winner is chosen, run the full set with:
  ```bash
  OPENAI_MODEL=<winner> python scripts/llm_screen_abstracts.py \
    --input  data/validation_screening_set.jsonl \
    --output data/pilot/<winner>_full.jsonl \
    --workers 4 --no-response-format [--thinking|--no-thinking]
  ```
