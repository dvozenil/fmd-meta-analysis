#!/usr/bin/env python3
"""Quick accuracy check for a pilot screening output file.

Usage:
    python scripts/check_pilot_results.py data/pilot/gemma4_thinking_on.jsonl
    python scripts/check_pilot_results.py --gold data/validation_screening_set.jsonl data/pilot/*.jsonl
"""

import argparse
import json
from pathlib import Path


def _load_gold(path: Path) -> dict[str, str]:
    """Load external gold labels: record_id -> human_gold_decision."""
    labels: dict[str, str] = {}
    for line in path.open():
        if not line.strip():
            continue
        rec = json.loads(line)
        decision = rec.get("human_gold_decision")
        if decision:
            labels[rec["record_id"]] = decision
    return labels


def check(path: Path, gold: dict[str, str] | None = None) -> None:
    records = [json.loads(l) for l in path.open() if l.strip()]

    def _gold_decision(r: dict) -> str | None:
        rid = r.get("record_id", "")
        if gold is not None:
            return gold.get(rid)
        return r.get("input_record", {}).get("human_gold_decision")

    strict = [r for r in records if _gold_decision(r) == "include_candidate"]
    broad = [r for r in records if _gold_decision(r) == "include_broad_scope"]
    errors = sum(1 for r in records if r.get("llm_decision") is None)

    model = records[0].get("source", {}).get("model", "?") if records else "?"
    thinking = records[0].get("source", {}).get("thinking") if records else "?"

    def _hits(subset: list[dict]) -> tuple[int, int, list[dict]]:
        tp = sum(1 for r in subset
                 if (r.get("llm_decision") or {}).get("decision") == "include_candidate")
        fn = len(subset) - tp
        missed = [r for r in subset
                  if (r.get("llm_decision") or {}).get("decision") != "include_candidate"]
        return tp, fn, missed

    tp, fn, fn_details = _hits(strict)
    tp_b, fn_b, fn_b_details = _hits(broad)

    print(f"File:                 {path}")
    print(f"Model:                {model}  (thinking={thinking})")
    print(f"Total records:        {len(records)}")
    print(f"Strict includes:      {tp}/{tp + fn}  (missed: {fn})")
    sens = f"{tp / (tp + fn):.0%}" if (tp + fn) else "n/a"
    print(f"Strict sensitivity:   {sens}")
    if broad:
        print(f"Broad-scope includes: {tp_b}/{tp_b + fn_b}  (missed: {fn_b})")
    print(f"API errors:           {errors}/{len(records)}")

    if fn_details:
        print(f"Missed (strict):")
        for r in fn_details:
            ref = r.get("input_record", {}).get("os_study_ref") or ""
            reason = (r.get("llm_decision") or {}).get("reason", "?")
            print(f"  {r['record_id']:25s} {ref:30s} -> {reason[:80]}")
    if fn_b_details:
        print(f"Missed (broad-scope):")
        for r in fn_b_details:
            ref = r.get("input_record", {}).get("os_study_ref") or ""
            reason = (r.get("llm_decision") or {}).get("reason", "?")
            print(f"  {r['record_id']:25s} {ref:30s} -> {reason[:80]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--gold", type=Path, default=None,
        help="External gold-label JSONL (overrides embedded input_record labels).",
    )
    args = parser.parse_args()

    gold = _load_gold(args.gold) if args.gold else None
    if gold:
        print(f"Using external gold labels from {args.gold} ({len(gold)} labelled records)\n")

    for path in args.files:
        check(path, gold)
        print()


if __name__ == "__main__":
    main()
