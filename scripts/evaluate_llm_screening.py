#!/usr/bin/env python3
"""Evaluate LLM screening JSONL outputs against human labels.

This script treats title/abstract screening as a binary retrieval problem:
records that should be sent forward are positive, records that should be
discarded are negative. Human/model "unclear" labels can be handled as positive,
negative, or dropped from evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    dropped_gold: int = 0
    missing_or_error: int = 0
    schema_warnings: int = 0

    @property
    def evaluated(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    def metric_row(self, model_name: str) -> dict[str, Any]:
        sensitivity = self.tp / (self.tp + self.fn) if (self.tp + self.fn) else None
        specificity = self.tn / (self.tn + self.fp) if (self.tn + self.fp) else None
        precision = self.tp / (self.tp + self.fp) if (self.tp + self.fp) else None
        accuracy = (self.tp + self.tn) / self.evaluated if self.evaluated else None
        f1 = (
            2 * precision * sensitivity / (precision + sensitivity)
            if precision is not None
            and sensitivity is not None
            and (precision + sensitivity)
            else None
        )
        return {
            "model_file": model_name,
            "evaluated": self.evaluated,
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "sensitivity": sensitivity,
            "specificity": specificity,
            "precision": precision,
            "accuracy": accuracy,
            "f1": f1,
            "dropped_gold": self.dropped_gold,
            "missing_or_error": self.missing_or_error,
            "schema_warning_rows": self.schema_warnings,
        }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def decision_to_binary(decision: str | None, unclear_policy: str) -> bool | None:
    if decision == "include_candidate":
        return True
    if decision == "exclude":
        return False
    if decision == "unclear":
        if unclear_policy == "positive":
            return True
        if unclear_policy == "negative":
            return False
        if unclear_policy == "drop":
            return None
    return None


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if not record_id:
            raise ValueError(f"Gold row missing record_id: {row}")
        decision = row.get("human_gold_decision")
        if decision not in {"include_candidate", "exclude", "unclear"}:
            raise ValueError(f"Bad human_gold_decision for {record_id}: {decision!r}")
        gold[record_id] = row
    return gold


def load_model(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if record_id:
            out[record_id] = row
    return out


def evaluate_one(
    gold: dict[str, dict[str, Any]],
    model_rows: dict[str, dict[str, Any]],
    gold_unclear_policy: str,
    model_unclear_policy: str,
) -> tuple[Counts, list[dict[str, Any]]]:
    counts = Counts()
    disagreements: list[dict[str, Any]] = []

    for record_id, gold_row in gold.items():
        gold_decision = gold_row.get("human_gold_decision")
        gold_binary = decision_to_binary(gold_decision, gold_unclear_policy)
        if gold_binary is None:
            counts.dropped_gold += 1
            continue

        model_row = model_rows.get(record_id)
        if not model_row or model_row.get("llm_decision") is None:
            counts.missing_or_error += 1
            disagreements.append(
                {
                    "record_id": record_id,
                    "title": gold_row.get("title", ""),
                    "gold": gold_decision,
                    "model": "missing_or_error",
                    "note": model_row.get("error") if model_row else "missing row",
                }
            )
            continue

        counts.schema_warnings += 1 if model_row.get("schema_warnings") else 0
        model_decision = model_row["llm_decision"].get("decision")
        model_binary = decision_to_binary(model_decision, model_unclear_policy)
        if model_binary is None:
            counts.missing_or_error += 1
            disagreements.append(
                {
                    "record_id": record_id,
                    "title": gold_row.get("title", ""),
                    "gold": gold_decision,
                    "model": model_decision,
                    "note": "model decision dropped/unusable",
                }
            )
            continue

        if gold_binary and model_binary:
            counts.tp += 1
        elif not gold_binary and model_binary:
            counts.fp += 1
        elif not gold_binary and not model_binary:
            counts.tn += 1
        elif gold_binary and not model_binary:
            counts.fn += 1

        if gold_binary != model_binary:
            disagreements.append(
                {
                    "record_id": record_id,
                    "title": gold_row.get("title", ""),
                    "gold": gold_decision,
                    "model": model_decision,
                    "gold_note": gold_row.get("human_gold_notes", ""),
                    "model_reason": model_row["llm_decision"].get("reason", ""),
                }
            )

    return counts, disagreements


def fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=Path("data/test_abstracts_20.jsonl"))
    parser.add_argument(
        "--results",
        type=Path,
        nargs="+",
        default=sorted(Path("data").glob("llm_screening_results_*.jsonl")),
    )
    parser.add_argument(
        "--gold-unclear-policy",
        choices=["positive", "negative", "drop"],
        default="negative",
        help="How to binarize human unclear labels.",
    )
    parser.add_argument(
        "--model-unclear-policy",
        choices=["positive", "negative", "drop"],
        default="positive",
        help="How to binarize model unclear labels.",
    )
    parser.add_argument("--output-csv", type=Path, default=Path("data/evaluation_summary.csv"))
    parser.add_argument(
        "--disagreements-jsonl",
        type=Path,
        default=Path("data/evaluation_disagreements.jsonl"),
    )
    args = parser.parse_args()

    gold = load_gold(args.gold)
    summary_rows: list[dict[str, Any]] = []
    all_disagreements: list[dict[str, Any]] = []

    for result_path in args.results:
        if result_path.name.endswith("_OLD.jsonl"):
            continue
        model_rows = load_model(result_path)
        counts, disagreements = evaluate_one(
            gold,
            model_rows,
            args.gold_unclear_policy,
            args.model_unclear_policy,
        )
        row = counts.metric_row(result_path.name)
        summary_rows.append(row)
        for disagreement in disagreements:
            disagreement["model_file"] = result_path.name
            all_disagreements.append(disagreement)

    summary_rows.sort(
        key=lambda r: (
            r["sensitivity"] if r["sensitivity"] is not None else -1,
            r["specificity"] if r["specificity"] is not None else -1,
            r["accuracy"] if r["accuracy"] is not None else -1,
        ),
        reverse=True,
    )

    write_csv(summary_rows, args.output_csv)
    args.disagreements_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.disagreements_jsonl.open("w", encoding="utf-8") as f:
        for row in all_disagreements:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        "Policy: "
        f"gold unclear={args.gold_unclear_policy}, "
        f"model unclear={args.model_unclear_policy}"
    )
    print(
        "model_file,evaluated,tp,fp,tn,fn,sensitivity,specificity,"
        "precision,accuracy,f1,missing_or_error,schema_warning_rows"
    )
    for row in summary_rows:
        print(
            ",".join(
                fmt(row[key])
                for key in [
                    "model_file",
                    "evaluated",
                    "tp",
                    "fp",
                    "tn",
                    "fn",
                    "sensitivity",
                    "specificity",
                    "precision",
                    "accuracy",
                    "f1",
                    "missing_or_error",
                    "schema_warning_rows",
                ]
            )
        )
    print(f"Wrote {args.output_csv}")
    print(f"Wrote {args.disagreements_jsonl}")


if __name__ == "__main__":
    main()
