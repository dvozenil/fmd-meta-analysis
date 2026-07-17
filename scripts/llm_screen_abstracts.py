#!/usr/bin/env python3
"""Screen abstracts with any OpenAI-compatible chat-completions API.

Environment variables:
  OPENAI_API_KEY      API key. For LM Studio, any non-empty value is fine.
  OPENAI_BASE_URL     Default: https://api.openai.com/v1
  OPENAI_MODEL        Default: gpt-4.1-mini

LM Studio example:
  OPENAI_API_KEY=lm-studio \
  OPENAI_BASE_URL=http://localhost:1234/v1 \
  OPENAI_MODEL=local-model \
  python scripts/llm_screen_abstracts.py --input data/test_abstracts_20.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


_DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "neuroimaging_v1.txt"

SYSTEM_PROMPT = """You are screening titles and abstracts for a systematic review/meta-analysis of neuroimaging studies in Functional Neurological Disorder (FND).

Goal: high-sensitivity title/abstract screening. Do not exclude plausible studies just because the abstract omits details that may appear in the full text.

Include candidate if the abstract plausibly describes:
- I1: Human adults with FND/conversion disorder/functional neurological symptom disorder, including motor FND, PNES/functional seizures, functional sensory symptoms, mixed FND, or close legacy terms.
- I2: A neuroimaging method relevant to brain structure or function, including fMRI, MRI/sMRI, VBM, cortical thickness, DTI/diffusion, PET, SPECT, resting-state, or connectivity.
- I3: Primary empirical research.

Exclude if clearly:
- E1: Not FND/conversion/functional neurological symptoms.
- E2: Not neuroimaging of the brain.
- E3: Review/editorial/commentary/protocol only.
- E4: Animal-only, pediatric-only, or case report only.
- E5: Treatment/social/clinical paper with no neuroimaging data.

For every response, populate inclusion_criteria_applied with the IDs (I1, I2, I3) of inclusion criteria the study appears to meet, and exclusion_criteria_applied with the IDs (E1–E5) of exclusion criteria that clearly apply. If none apply, use an empty array [].

Coordinates are usually not visible in abstracts. Mark coordinate_present and coordinate_space as "unclear" unless the abstract explicitly says MNI/Talairach/coordinates/peak coordinates.

Use exactly the allowed enum strings below. Do not invent new tag names. Do not combine multiple exclusion reasons into one string; choose the primary reason. Do not wrap the JSON in markdown fences.

Set needs_human_review to true for every include_candidate or unclear decision. Set it to false only for a high-confidence, obvious exclusion.

Return exactly one JSON object with this schema:
{
  "decision": "include_candidate | exclude | unclear",
  "confidence": 0.0,
  "reason": "short rationale",
  "exclusion_reason": "wrong_population | wrong_modality | not_primary_research | pediatric_only | case_report | no_human_data | not_fnd | other | null",
  "inclusion_criteria_applied": ["I1", "I2", "I3"],
  "exclusion_criteria_applied": ["E1", "E2", "E3", "E4", "E5"],
  "modality_tags": ["fMRI | sMRI | VBM | PET | SPECT | DTI | resting_state | connectivity | EEG | other"],
  "population_tags": ["FND | PNES | functional_movement | functional_sensory | mixed | other"],
  "design_tags": ["case_control | within_subject | longitudinal | randomized_trial | review | case_report | protocol | other"],
  "coordinate_present": "yes | no | unclear",
  "coordinate_space": "MNI | Talairach | unknown | unclear | not_reported",
  "needs_human_review": true
}
"""


def _load_prompt(prompt_path: Path | None) -> str:
    """Load system prompt from file, falling back to the embedded default."""
    if prompt_path is not None:
        return prompt_path.read_text(encoding="utf-8").strip()
    return SYSTEM_PROMPT.strip()


ALLOWED_VALUES = {
    "decision": {"include_candidate", "exclude", "unclear"},
    "exclusion_reason": {
        "wrong_population",
        "wrong_modality",
        "not_primary_research",
        "pediatric_only",
        "case_report",
        "no_human_data",
        "not_fnd",
        "other",
        None,
    },
    "coordinate_present": {"yes", "no", "unclear"},
    "coordinate_space": {"MNI", "Talairach", "unknown", "unclear", "not_reported"},
}

ALLOWED_TAGS = {
    "modality_tags": {
        "fMRI",
        "sMRI",
        "VBM",
        "PET",
        "SPECT",
        "DTI",
        "resting_state",
        "connectivity",
        "EEG",
        "other",
    },
    "population_tags": {
        "FND",
        "PNES",
        "functional_movement",
        "functional_sensory",
        "mixed",
        "other",
    },
    "design_tags": {
        "case_control",
        "within_subject",
        "longitudinal",
        "randomized_trial",
        "review",
        "case_report",
        "protocol",
        "other",
    },
}

VALUE_NORMALIZATIONS = {
    ("exclusion_reason", "review"): "not_primary_research",
    ("population_tags", "conversion disorder"): "FND",
    ("modality_tags", "MRI"): "sMRI",
    ("modality_tags", "CT"): "other",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


_write_lock = threading.Lock()


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def completed_record_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("llm_decision") is not None:
                    done.add(row["record_id"])
            except Exception:
                continue
    return done


def _strip_control_chars(text: str) -> str:
    """Remove ASCII control characters (except newline/tab) that some models emit."""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


def extract_json_object(text: str) -> dict[str, Any]:
    text = _strip_control_chars(text)
    start = text.rfind("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return json.loads(text)


def normalize_and_validate_decision(decision: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    for key in ("decision", "exclusion_reason", "coordinate_present", "coordinate_space"):
        value = decision.get(key)
        normalized = VALUE_NORMALIZATIONS.get((key, value), value)
        if normalized != value:
            decision[key] = normalized
            warnings.append(f"normalized {key}: {value!r} -> {normalized!r}")

    for key in ("modality_tags", "population_tags", "design_tags"):
        tags = decision.get(key)
        if not isinstance(tags, list):
            decision[key] = []
            warnings.append(f"{key} was not a list")
            continue
        normalized_tags = []
        for tag in tags:
            normalized_tags.append(VALUE_NORMALIZATIONS.get((key, tag), tag))
        decision[key] = normalized_tags

    for key in ("inclusion_criteria_applied", "exclusion_criteria_applied"):
        val = decision.get(key)
        if not isinstance(val, list):
            decision[key] = []
            if val is not None:
                warnings.append(f"{key} was not a list, reset to []")
        else:
            decision[key] = [v for v in val if isinstance(v, str)]

    if decision.get("decision") in {"include_candidate", "unclear"}:
        if decision.get("needs_human_review") is not True:
            decision["needs_human_review"] = True
            warnings.append("normalized needs_human_review to true for non-exclude decision")

    if decision.get("decision") != "exclude" and decision.get("exclusion_reason") is not None:
        decision["exclusion_reason"] = None
        warnings.append("normalized exclusion_reason to null for non-exclude decision")

    for key, allowed in ALLOWED_VALUES.items():
        if decision.get(key) not in allowed:
            warnings.append(f"invalid {key}: {decision.get(key)!r}")

    for key, allowed in ALLOWED_TAGS.items():
        bad_tags = [tag for tag in decision.get(key, []) if tag not in allowed]
        if bad_tags:
            warnings.append(f"invalid {key}: {bad_tags!r}")

    confidence = decision.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        warnings.append(f"invalid confidence: {confidence!r}")

    if not isinstance(decision.get("needs_human_review"), bool):
        warnings.append(f"invalid needs_human_review: {decision.get('needs_human_review')!r}")

    return decision, warnings


def build_user_prompt(record: dict[str, Any]) -> str:
    return json.dumps(
        {
            "record_id": record.get("record_id"),
            "title": record.get("title"),
            "abstract": record.get("abstract"),
            "journal": record.get("journal"),
            "year": record.get("year"),
            "authors": record.get("authors"),
        },
        ensure_ascii=False,
        indent=2,
    )


def call_model(
    record: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    max_retries: int,
    use_response_format: bool,
    thinking: bool | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Call the model once for one record.

    ``thinking`` controls ``chat_template_kwargs``:
      - None  → omit the key entirely (server default)
      - True  → ``{"thinking": true, "enable_thinking": true}``
      - False → ``{"thinking": false, "enable_thinking": false}``

    Both ``thinking`` and ``enable_thinking`` are sent together because
    different model families use different key names.
    """
    prompt_text = system_prompt or SYSTEM_PROMPT
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": build_user_prompt(record)},
        ],
    }
    if thinking is not None:
        payload["chat_template_kwargs"] = {
            "thinking": thinking,
            "enable_thinking": thinking,
        }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}

    last_error: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 429:
                retry_after = int(float(response.headers.get("retry-after", "5")))
                time.sleep(retry_after)
                continue
            if response.status_code == 400 and "response_format" in response.text:
                payload.pop("response_format", None)
                continue
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise ValueError(f"empty model content; response={json.dumps(data)[:1000]}")
            parsed = extract_json_object(content)
            if not isinstance(parsed, dict):
                raise ValueError(f"model content did not parse to a JSON object: {content[:500]}")
            parsed, schema_warnings = normalize_and_validate_decision(parsed)
            return {
                "record_id": record["record_id"],
                "source": {
                    "model": model,
                    "base_url": base_url,
                    "thinking": thinking,
                },
                "input_record": record,
                "llm_decision": parsed,
                "schema_warnings": schema_warnings,
                "raw_response": content,
            }
        except Exception as exc:
            last_error = str(exc)
            with suppress(Exception):
                if "response" in locals() and response is not None:
                    last_error = f"{last_error}; response_body={response.text[:1000]}"
            time.sleep(2 ** (attempt - 1))

    return {
        "record_id": record["record_id"],
        "source": {
            "model": model,
            "base_url": base_url,
            "thinking": thinking,
        },
        "input_record": record,
        "llm_decision": None,
        "error": last_error or "unknown model/API error",
    }


def _decision_order(decision: str) -> int:
    """Ordinal for sorting: include_candidate > unclear > exclude."""
    order = {"include_candidate": 2, "unclear": 1, "exclude": 0}
    return order.get(decision, -1)


def call_model_with_reps(
    record: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    timeout: int,
    max_retries: int,
    use_response_format: bool,
    reps: int,
    thinking: bool | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Call the model ``reps`` times for one record and return consensus.

    Each repetition is an independent call. Results are aggregated into a
    consensus decision using majority vote on the three-way decision
    (include_candidate / exclude / unclear).  When there is a tie the
    most-inclusive option wins (include_candidate > unclear > exclude).

    Returns the same shape as ``call_model``, extended with:

    - ``consensus_decision``: the aggregated decision
    - ``consensus_confidence``: fraction of reps that voted for the consensus
    - ``consensus_counts``: ``{decision: count}`` across all reps
    - ``individual_runs``: list of the per-rep result dicts
    - ``failed_runs``: count of reps that returned an error
    """
    individual_runs: list[dict[str, Any]] = []
    for rep in range(1, reps + 1):
        result = call_model(
            record,
            base_url,
            api_key,
            model,
            temperature,
            timeout,
            max_retries,
            use_response_format,
            thinking,
            system_prompt,
        )
        result["_rep"] = rep
        individual_runs.append(result)

    # Count decisions from successful runs
    from collections import Counter
    dec_counter: Counter[str] = Counter()
    successes = [r for r in individual_runs if r.get("llm_decision") is not None]
    failures = len(individual_runs) - len(successes)

    for r in successes:
        dec_counter[r["llm_decision"]["decision"]] += 1

    if not successes:
        # All runs failed — pick the last result as the error carrier
        last = individual_runs[-1]
        return {
            "record_id": record["record_id"],
            "source": last["source"],
            "input_record": record,
            "llm_decision": None,
            "error": last.get("error", "all repetitions failed"),
            "consensus_decision": None,
            "consensus_confidence": 0.0,
            "consensus_counts": {},
            "individual_runs": individual_runs,
            "failed_runs": failures,
        }

    # Majority vote; break ties toward inclusivity
    sorted_decs = sorted(dec_counter.keys(), key=_decision_order, reverse=True)
    consensus = max(sorted_decs, key=lambda d: dec_counter[d])
    confidence = dec_counter[consensus] / reps

    # Use the first run that matched the consensus as the primary decision
    primary = next(
        (r for r in successes if r["llm_decision"]["decision"] == consensus),
        successes[0],
    )

    return {
        "record_id": record["record_id"],
        "source": primary["source"],
        "input_record": record,
        "llm_decision": primary["llm_decision"],
        "schema_warnings": primary.get("schema_warnings", []),
        "raw_response": primary.get("raw_response"),
        "consensus_decision": consensus,
        "consensus_confidence": confidence,
        "consensus_counts": dict(dec_counter),
        "individual_runs": individual_runs,
        "failed_runs": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/llm_screening_results.jsonl"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--no-response-format",
        action="store_true",
        help="Do not send response_format=json_object; useful for local servers that reject it.",
    )
    parser.add_argument(
        "--prompt", type=Path, default=None,
        help="Path to a prompt text file (overrides the built-in neuroimaging prompt).",
    )
    thinking_group = parser.add_mutually_exclusive_group()
    thinking_group.add_argument(
        "--thinking",
        action="store_true",
        default=None,
        help="Pass chat_template_kwargs thinking=true/enable_thinking=true (force reasoning on).",
    )
    thinking_group.add_argument(
        "--no-thinking",
        action="store_true",
        default=None,
        help="Pass chat_template_kwargs thinking=false/enable_thinking=false (force reasoning off).",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=1,
        metavar="N",
        help="Repeat each screening N times, take majority-vote consensus "
        "(default: 1, no repeats). 3 recommended for production screening. "
        "See Vembye et al. (2025, Psychological Methods) for validation of "
        "repeated-questioning protocols for LLM title/abstract screening.",
    )
    args = parser.parse_args()

    if args.thinking:
        thinking: bool | None = True
    elif args.no_thinking:
        thinking = False
    else:
        thinking = None

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        print("OPENAI_API_KEY is required. For LM Studio, set it to any non-empty string.", file=sys.stderr)
        sys.exit(2)

    loaded_prompt = _load_prompt(args.prompt)
    if args.prompt:
        print(f"Using prompt from: {args.prompt}")

    records = read_jsonl(args.input)
    done = completed_record_ids(args.output)
    todo = [r for r in records if r.get("record_id") not in done]

    print(f"Loaded {len(records)} records; {len(done)} already completed; {len(todo)} to screen.")
    if args.reps > 1:
        print(f"Repeated screening: {args.reps} queries per abstract, majority-vote consensus.")
    if not todo:
        return

    _call_fn = call_model if args.reps <= 1 else call_model_with_reps
    _extra = {} if args.reps <= 1 else {"reps": args.reps}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(
                _call_fn,
                record,
                base_url,
                api_key,
                model,
                args.temperature,
                args.timeout,
                args.max_retries,
                not args.no_response_format,
                thinking,
                loaded_prompt,
                **_extra,
            )
            for record in todo
        ]
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            result = future.result()
            append_jsonl(args.output, result)
            if args.reps > 1:
                c = result.get("consensus_counts", {})
                conf = result.get("consensus_confidence", 0.0)
                status = f"consensus={result.get('consensus_decision')} "
                status += f"({c.get('include_candidate', 0)}i/{c.get('unclear', 0)}u/{c.get('exclude', 0)}e) "
                status += f"conf={conf:.0%}"
            else:
                status = "ok" if result.get("llm_decision") else "error"
            print(f"[{i}/{len(todo)}] {status}: {result['record_id']}")


if __name__ == "__main__":
    main()
