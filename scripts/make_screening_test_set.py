#!/usr/bin/env python3
"""Build a small title/abstract screening test set.

Use this after an os_validation search run:

    python scripts/make_screening_test_set.py \
        --input fnd_search_YYYYMMDD_HHMMSS/records_deduplicated.csv

The script tries to include records matching known Boeckle et al. (2016)
meta-analysis studies, then fills the remaining slots with random records.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from pathlib import Path
from typing import Any


DEFAULT_OS_INCLUDED_PATTERNS = [
    # These are intentionally partial title/author patterns so they survive
    # small database-format differences. Treat as a seed list, not ground truth.
    "vuilleumier",
    "spence",
    "marshall",
    "stone",
    "van beilen",
    "voon",
    "aybek",
    "elzinga",
    "czarnecki",
    "the involuntary nature of conversion disorder",
    "hysterical paralysis",
    "motor conversion disorder",
    "psychogenic paralysis",
]


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def load_patterns(path: Path | None) -> list[str]:
    if not path:
        return DEFAULT_OS_INCLUDED_PATTERNS
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def has_abstract(record: dict[str, Any]) -> bool:
    return bool(record.get("abstract", "").strip())


def matches_os_seed(record: dict[str, Any], patterns: list[str]) -> bool:
    haystack = normalize(
        " ".join(
            [
                record.get("title", ""),
                record.get("authors", ""),
                record.get("journal", ""),
                str(record.get("year", "")),
            ]
        )
    )
    return any(normalize(pattern) in haystack for pattern in patterns)


def to_screening_item(record: dict[str, Any], label_source: str) -> dict[str, Any]:
    record_id = f"{record.get('source_db', '')}:{record.get('source_id', '')}"
    return {
        "record_id": record_id,
        "source_db": record.get("source_db", ""),
        "source_id": record.get("source_id", ""),
        "doi": record.get("doi") or None,
        "title": record.get("title", ""),
        "abstract": record.get("abstract", ""),
        "authors": record.get("authors", ""),
        "journal": record.get("journal", ""),
        "year": int(record["year"]) if str(record.get("year", "")).isdigit() else None,
        "url": record.get("url", ""),
        "label_source": label_source,
        "human_gold_decision": None,
        "human_gold_notes": "",
    }


def write_jsonl(items: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/test_abstracts_20.jsonl"))
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--os-n", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--os-patterns",
        type=Path,
        help="Optional newline-delimited title/author patterns for known OS includes.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    patterns = load_patterns(args.os_patterns)
    all_records = [r for r in read_records(args.input) if has_abstract(r)]

    os_matches = [r for r in all_records if matches_os_seed(r, patterns)]
    rng.shuffle(os_matches)
    selected_os = os_matches[: args.os_n]

    selected_keys = {
        (r.get("source_db", ""), r.get("source_id", ""), r.get("title", ""))
        for r in selected_os
    }
    remaining = [
        r
        for r in all_records
        if (r.get("source_db", ""), r.get("source_id", ""), r.get("title", ""))
        not in selected_keys
    ]
    rng.shuffle(remaining)

    selected = [
        to_screening_item(r, "os_included_seed_match") for r in selected_os
    ]
    selected.extend(
        to_screening_item(r, "random_from_deduplicated_search")
        for r in remaining[: max(0, args.n - len(selected))]
    )

    write_jsonl(selected[: args.n], args.output)
    print(f"Wrote {len(selected[: args.n])} records -> {args.output}")
    print(f"OS seed matches available: {len(os_matches)}; selected: {len(selected_os)}")
    if len(selected_os) < args.os_n:
        print(
            "Warning: fewer OS seed matches than requested. "
            "Check the os_validation run and/or provide --os-patterns."
        )


if __name__ == "__main__":
    main()
