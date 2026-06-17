#!/usr/bin/env python3
"""Prepare a stratified random sample for human screening and a companion
comparison script.

Produces a CSV designed for spreadsheet use:
  - Left columns: record info needed for screening (title, abstract, etc.)
  - Empty human_decision / human_notes columns for the reviewer
  - Right columns (hidden during screening): LLM decision for later comparison

Usage:
    python scripts/prepare_human_screening_sample.py \
        data/pilot/qwen3_5_122b_thinking_off_FULL-VALIDATION.jsonl \
        --n 50 --seed 42
"""

import argparse
import csv
import json
import random
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open() if l.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--n", type=int, default=50, help="Total sample size")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output CSV path (default: data/human_screening_sample_<n>.csv)",
    )
    args = parser.parse_args()

    records = load(args.file)
    rng = random.Random(args.seed)

    non_gold = [
        r for r in records
        if not r.get("input_record", {}).get("human_gold_decision")
        and r.get("llm_decision") is not None
    ]

    includes = [r for r in non_gold if r["llm_decision"]["decision"] == "include_candidate"]
    excludes = [r for r in non_gold if r["llm_decision"]["decision"] == "exclude"]
    unclears = [r for r in non_gold if r["llm_decision"]["decision"] == "unclear"]

    # Stratified sample: over-sample includes so we can assess PPV,
    # but keep the majority excludes to also assess specificity.
    # Target: all includes (if ≤ 20), then fill rest with excludes + unclear.
    n_include = min(len(includes), 20)
    n_unclear = min(len(unclears), 5)
    n_exclude = args.n - n_include - n_unclear

    sample_inc = rng.sample(includes, n_include) if n_include <= len(includes) else includes
    sample_unc = rng.sample(unclears, n_unclear) if n_unclear <= len(unclears) else unclears
    sample_exc = rng.sample(excludes, min(n_exclude, len(excludes)))

    sample = sample_inc + sample_unc + sample_exc
    rng.shuffle(sample)

    out_path = args.output or Path(f"data/human_screening_sample_{len(sample)}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "row_num",
        "record_id",
        "title",
        "abstract",
        "authors",
        "journal",
        "year",
        "url",
        # human columns
        "human_decision",
        "human_notes",
        # LLM columns (hide during blind screening)
        "llm_decision",
        "llm_confidence",
        "llm_reason",
        "llm_exclusion_reason",
        "llm_population_tags",
        "llm_modality_tags",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, r in enumerate(sample, 1):
            inp = r.get("input_record", {})
            d = r["llm_decision"]
            writer.writerow({
                "row_num": i,
                "record_id": r["record_id"],
                "title": inp.get("title", ""),
                "abstract": inp.get("abstract", ""),
                "authors": inp.get("authors", ""),
                "journal": inp.get("journal", ""),
                "year": inp.get("year", ""),
                "url": inp.get("url", ""),
                "human_decision": "",
                "human_notes": "",
                "llm_decision": d.get("decision", ""),
                "llm_confidence": d.get("confidence", ""),
                "llm_reason": d.get("reason", ""),
                "llm_exclusion_reason": d.get("exclusion_reason", ""),
                "llm_population_tags": "; ".join(d.get("population_tags", [])),
                "llm_modality_tags": "; ".join(d.get("modality_tags", [])),
            })

    print(f"Sample written: {out_path}")
    print(f"  Total:    {len(sample)}")
    print(f"  Includes: {len(sample_inc)}")
    print(f"  Unclear:  {len(sample_unc)}")
    print(f"  Excludes: {len(sample_exc)}")
    print()
    print("Screening instructions:")
    print("  1. Open the CSV in a spreadsheet (Excel / Google Sheets).")
    print("  2. HIDE columns K–P (llm_*) to screen blind.")
    print("  3. For each row, read title + abstract and fill in:")
    print("     human_decision = include_candidate | exclude | unclear")
    print("     human_notes    = (optional) brief reason")
    print("  4. Save as CSV when done.")
    print("  5. Run: python scripts/compare_human_llm.py <your_csv>")


if __name__ == "__main__":
    main()
