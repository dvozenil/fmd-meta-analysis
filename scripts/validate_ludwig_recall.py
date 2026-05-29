#!/usr/bin/env python3
"""Cross-reference search results against Ludwig et al. (2018) included studies.

Produces:
  1. A markdown validation report.
  2. A JSONL screening file with known Ludwig includes pre-labeled,
     ready for LLM pipeline sensitivity testing.

Usage:
    python scripts/validate_ludwig_recall.py \
        --search-dir fnd_search_YYYYMMDD_HHMMSS \
        --ludwig-table data/ludwig_included_studies_resolved.csv

    # Or use the unresolved CSV (no DOI matching, title+author only):
    python scripts/validate_ludwig_recall.py \
        --search-dir fnd_search_YYYYMMDD_HHMMSS \
        --ludwig-table data/ludwig_included_studies.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi.rstrip(".")


def _title_words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z0-9\u00C0-\u024F]{3,}", text)}


def _title_jaccard(a: str, b: str) -> float:
    wa, wb = _title_words(a), _title_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _surname_is_author(surname: str, rec_authors: str) -> bool:
    authors_lower = rec_authors.lower()
    pattern = (
        r"(?<![a-z\u00c0-\u024f])"
        + re.escape(surname.lower())
        + r"(?![a-z\u00c0-\u024f])"
    )
    return bool(re.search(pattern, authors_lower))


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_ludwig_table(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    has_doi = "ref_doi" in rows[0] if rows else False
    for row in rows:
        entry: dict[str, str] = {
            "first_author": row["first_author"].strip(),
            "year": row.get("ref_year", row.get("year", "")).strip(),
            "title": row["title"].strip(),
            "journal": row.get("journal", "").strip(),
            "symptom_type": row.get("symptom_type", "").strip(),
            "n_fnd": row.get("n_fnd", "").strip(),
            "n_control": row.get("n_control", "").strip(),
            "ref_number": row["ref_number"].strip(),
            "ref_unstructured": row.get("ref_unstructured", "").strip(),
        }
        if has_doi:
            entry["ref_doi"] = _normalize_doi(row.get("ref_doi", ""))
        out.append(entry)
    return out


def load_search_records(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_ludwig_studies(
    studies: list[dict[str, str]],
    search_records: list[dict[str, Any]],
) -> tuple[list[dict], list[dict]]:
    """Match Ludwig studies to search records using DOI-first, then title+author."""
    found: list[dict] = []
    not_found: list[dict] = []
    used_indices: set[int] = set()
    unmatched: list[dict] = []

    has_ref_doi = any(s.get("ref_doi") for s in studies)

    rec_doi_index: dict[str, int] = {}
    if has_ref_doi:
        for idx, rec in enumerate(search_records):
            doi = _normalize_doi(rec.get("doi", ""))
            if doi:
                rec_doi_index[doi] = idx

    # --- Pass 1: DOI match ---
    for study in studies:
        ref_doi = study.get("ref_doi", "")
        if ref_doi and ref_doi in rec_doi_index:
            idx = rec_doi_index[ref_doi]
            if idx not in used_indices:
                used_indices.add(idx)
                found.append({
                    **study,
                    "matched_record": search_records[idx],
                    "match_method": "doi",
                })
                continue
        unmatched.append(study)

    # --- Pass 2: Title Jaccard + author surname ---
    still_unmatched: list[dict] = []
    for study in unmatched:
        best_idx: int | None = None
        best_score = 0.0
        surname = study["first_author"].lower()

        for idx, rec in enumerate(search_records):
            if idx in used_indices:
                continue
            rec_title = rec.get("title", "")
            score = _title_jaccard(study["title"], rec_title)
            if score > best_score and _surname_is_author(surname, rec.get("authors", "")):
                best_score = score
                best_idx = idx

        if best_score >= 0.45 and best_idx is not None:
            used_indices.add(best_idx)
            found.append({
                **study,
                "matched_record": search_records[best_idx],
                "match_method": f"title_jaccard({best_score:.2f})",
            })
        else:
            still_unmatched.append(study)

    # --- Pass 3: Surname + year + keyword fallback ---
    fnd_keywords = frozenset({
        "conversion", "dissociative", "functional", "psychogenic",
        "hysterical", "hysteria", "somatoform", "somatization",
        "seizure", "epileptic", "nonepileptic", "pseudoseizure",
        "abuse", "trauma", "maltreatment", "neglect", "stress",
        "stressor", "life event", "dysphonia", "voice",
    })
    for study in still_unmatched:
        surname = study["first_author"].lower()
        year = study["year"]

        matched_idx: int | None = None
        for idx, rec in enumerate(search_records):
            if idx in used_indices:
                continue
            if not _surname_is_author(surname, rec.get("authors", "")):
                continue
            if year and str(rec.get("year", "")) != year:
                continue
            title_words = _title_words(rec.get("title", ""))
            if fnd_keywords & title_words:
                matched_idx = idx
                break

        if matched_idx is not None:
            used_indices.add(matched_idx)
            found.append({
                **study,
                "matched_record": search_records[matched_idx],
                "match_method": "surname_year_keyword",
            })
        else:
            not_found.append(study)

    return found, not_found


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(
    found: list[dict],
    not_found: list[dict],
    total_studies: int,
    search_dir: str,
    per_db: dict[str, int],
    dedup_count: int,
) -> str:
    lines = [
        "# Ludwig et al. (2018) Search Validation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Search run: `{search_dir}`",
        "",
        "## Context",
        "",
        "This report validates whether our Ludwig-mode search strategy recovers",
        "the 34 case-control studies included in Ludwig et al. (2018) \"Stressful",
        "life events and maltreatment in conversion (functional neurological)",
        "disorder: systematic review and meta-analysis of case-control studies\"",
        "(*Lancet Psychiatry*, doi:10.1016/S2215-0366(18)30051-8).",
        "",
        "Ludwig searched PubMed and Science Direct from 1965 to Nov 4, 2016 using:",
        '`("psychogenic" OR "conversion disorder" OR "non-epileptic") AND ("abuse"',
        'OR "life event") AND ("control" OR "controlled" OR "case-control")`.',
        "",
        "They also identified 20 additional studies through reference-list chasing,",
        "so database-only recall below 100% is expected.",
        "",
        "### Per-database counts",
        "",
        "| Database | Records |",
        "| --- | ---: |",
    ]
    for db, n in per_db.items():
        lines.append(f"| {db} | {n} |")
    lines.extend([
        f"| **After deduplication** | **{dedup_count}** |",
        "",
        f"## Results: {len(found)}/{total_studies} studies found",
        "",
        "### Matched studies",
        "",
        "| # | Study | Year | Symptom type | Source DB | Match method |",
        "| ---: | --- | ---: | --- | --- | --- |",
    ])
    for i, s in enumerate(found, 1):
        rec = s["matched_record"]
        lines.append(
            f"| {i} | {s['first_author']} et al. | {s['year']} "
            f"| {s['symptom_type']} | {rec.get('source_db', '')} "
            f"| {s.get('match_method', 'legacy')} |"
        )

    if not_found:
        lines.extend([
            "",
            f"### Not found ({len(not_found)} studies)",
            "",
            "These studies were likely found by Ludwig via reference-list chasing",
            "or Science Direct (not directly replicated in our API search).",
            "",
            "| Study | Year | Symptom type | Journal |",
            "| --- | ---: | --- | --- |",
        ])
        for s in not_found:
            lines.append(
                f"| {s['first_author']} et al. | {s['year']} "
                f"| {s['symptom_type']} | {s['journal']} |"
            )

    lines.extend([
        "",
        "## Conclusion",
        "",
        f"Database search recovered **{len(found)}/{total_studies}** Ludwig-included",
        f"studies ({len(not_found)} not found).",
        "",
        "Unrecovered studies are expected: Ludwig identified 20 of their 1189",
        "initial records through reference-list chasing, and we do not search",
        "Science Direct directly (partially covered by Scopus and Europe PMC).",
        "",
        f"This validation set (with the {len(found)} matched studies marked as known",
        "includes) is used downstream to test LLM screening pipeline sensitivity.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------

def build_screening_jsonl(
    search_records: list[dict[str, Any]],
    found: list[dict],
) -> list[dict[str, Any]]:
    matched_keys = set()
    ludwig_ref_by_key: dict[tuple, str] = {}
    for entry in found:
        rec = entry["matched_record"]
        key = (rec.get("source_db", ""), rec.get("source_id", ""), rec.get("title", ""))
        matched_keys.add(key)
        ludwig_ref_by_key[key] = f"{entry['first_author']} et al. ({entry['year']}) [ref {entry['ref_number']}]"

    items = []
    for rec in search_records:
        key = (rec.get("source_db", ""), rec.get("source_id", ""), rec.get("title", ""))
        is_match = key in matched_keys

        items.append({
            "record_id": f"{rec.get('source_db', '')}:{rec.get('source_id', '')}",
            "source_db": rec.get("source_db", ""),
            "source_id": rec.get("source_id", ""),
            "doi": rec.get("doi") or None,
            "title": rec.get("title", ""),
            "abstract": rec.get("abstract", ""),
            "authors": rec.get("authors", ""),
            "journal": rec.get("journal", ""),
            "year": int(rec["year"]) if str(rec.get("year", "")).isdigit() else None,
            "url": rec.get("url", ""),
            "label_source": "ludwig_table_match" if is_match else "search_result",
            "human_gold_decision": "include_candidate" if is_match else None,
            "human_gold_notes": "",
            "ludwig_study_ref": ludwig_ref_by_key.get(key),
        })

    return items


def write_jsonl(items: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate search recall against Ludwig et al. (2018) included studies"
    )
    parser.add_argument(
        "--search-dir", type=Path, required=True,
        help="Path to the search run directory (e.g. fnd_search_YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--ludwig-table", type=Path,
        default=Path("data/ludwig_included_studies_resolved.csv"),
        help="Path to the Ludwig included studies CSV",
    )
    parser.add_argument(
        "--output-report", type=Path,
        default=Path("docs/ludwig_validation_report.md"),
    )
    parser.add_argument(
        "--output-jsonl", type=Path,
        default=Path("data/ludwig_validation_set.jsonl"),
    )
    args = parser.parse_args()

    csv_path = args.search_dir / "records_deduplicated.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No records_deduplicated.csv in {args.search_dir}")

    meta_path = args.search_dir / "prisma_search_metadata.json"
    per_db: dict[str, int] = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        per_db = meta.get("records_per_database", {})

    ludwig_studies = load_ludwig_table(args.ludwig_table)
    search_records = load_search_records(csv_path)

    found, not_found = match_ludwig_studies(ludwig_studies, search_records)

    report = generate_report(
        found, not_found,
        total_studies=len(ludwig_studies),
        search_dir=args.search_dir.name,
        per_db=per_db,
        dedup_count=len(search_records),
    )
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print(f"Wrote validation report -> {args.output_report}")

    screening_items = build_screening_jsonl(search_records, found)
    write_jsonl(screening_items, args.output_jsonl)
    gold_count = sum(1 for it in screening_items if it["human_gold_decision"])
    print(f"Wrote {len(screening_items)} records -> {args.output_jsonl}")
    print(f"  {gold_count} records marked as known Ludwig includes")
    print(f"  {len(screening_items) - gold_count} records with no gold label")

    print(f"\nRecall: {len(found)}/{len(ludwig_studies)}")
    if not_found:
        print(f"Not found ({len(not_found)}):")
        for s in not_found:
            print(f"  {s['first_author']} ({s['year']}): {s['title'][:60]}")


if __name__ == "__main__":
    main()
