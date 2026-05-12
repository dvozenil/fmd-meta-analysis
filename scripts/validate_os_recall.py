#!/usr/bin/env python3
"""Cross-reference search results against Boeckle et al. (2016) Table 1.

Produces:
  1. A markdown validation report (supplementary material).
  2. A JSONL screening file with known OS includes pre-labeled,
     ready for LLM pipeline sensitivity testing.

Usage:
    python scripts/validate_os_recall.py \
        --search-dir fnd_search_20260512_154542 \
        --output-report docs/os_validation_report.md \
        --output-jsonl data/validation_screening_set.jsonl
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

def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", text)}


FND_KEYWORDS = frozenset({
    "conversion", "dissociative", "functional", "psychogenic",
    "hysterical", "hysteria", "somatoform", "somatization",
    "dysmorphic", "pnes", "seizure", "epileptic", "dystonia",
    "tremor", "paralysis", "motor", "sensory", "astasia",
    "movement", "neurological", "nonepileptic",
})


def _extract_surname(study_field: str) -> str:
    s = study_field.lstrip("a")
    m = re.match(r"([A-Za-z\s\-]+)", s)
    return m.group(1).strip().lower() if m else ""


def _match_record(surname: str, disorder: str,
                  rec_authors: str, rec_title: str) -> bool:
    """True if surname is in the author list and there is FND-relevant
    keyword overlap between the OS disorder label and the record title."""
    authors_lower = rec_authors.lower()
    if surname not in authors_lower and surname.replace(" ", "") not in authors_lower:
        return False
    title_words = _words(rec_title)
    disorder_words = _words(disorder)
    return bool(disorder_words & title_words) or bool(FND_KEYWORDS & title_words)


def _categorize_miss(disorder: str, imaging: str) -> str:
    """Classify a miss into an explanatory category."""
    img_lower = imaging.lower()
    dis_lower = disorder.lower()

    eeg_meg_ct = (
        re.search(r"\bEEG\b", imaging, re.IGNORECASE)
        or re.search(r"\bMEG\b", imaging, re.IGNORECASE)
        or re.search(r"\bCT\b", imaging, re.IGNORECASE)
    )
    if eeg_meg_ct and not re.search(r"\bSPECT\b", imaging, re.IGNORECASE):
        return "out_of_scope_imaging"

    non_fnd = any(x in dis_lower for x in [
        "dysmorphic", "somatization", "somatoform",
        "dissociative identity", "dissociative ptsd",
        "non clinical dissociative", "dissociation des",
        "syncope",
    ])
    if non_fnd:
        return "out_of_scope_disorder"

    return "in_scope_miss"


CATEGORY_LABELS = {
    "out_of_scope_imaging": "Out-of-scope imaging modality (EEG / MEG / CT)",
    "out_of_scope_disorder": "Out-of-scope disorder (not FND)",
    "in_scope_miss": "In-scope miss (investigate search terms)",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_os_table(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        out.append({
            "study": row["Study"].strip().strip('"'),
            "surname": _extract_surname(row["Study"].strip().strip('"')),
            "disorder": row["Disorder"].strip(),
            "imaging": row["Imaging method"].strip(),
        })
    return out


def load_search_records(path: Path) -> list[dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match_os_studies(
    os_studies: list[dict[str, str]],
    search_records: list[dict[str, Any]],
) -> tuple[list[dict], list[dict]]:
    found, not_found = [], []
    used_indices: set[int] = set()

    for study in os_studies:
        matched_rec = None
        matched_idx = None
        for idx, rec in enumerate(search_records):
            if idx in used_indices:
                continue
            if _match_record(
                study["surname"],
                study["disorder"],
                rec.get("authors", ""),
                rec.get("title", ""),
            ):
                matched_rec = rec
                matched_idx = idx
                break

        entry = {**study}
        if matched_rec is not None:
            assert matched_idx is not None
            used_indices.add(matched_idx)
            entry["matched_record"] = matched_rec
            found.append(entry)
        else:
            entry["category"] = _categorize_miss(study["disorder"], study["imaging"])
            not_found.append(entry)

    return found, not_found


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    found: list[dict],
    not_found: list[dict],
    total_os: int,
    search_dir: str,
    per_db: dict[str, int],
    dedup_count: int,
) -> str:
    cats = {}
    for miss in not_found:
        cat = miss["category"]
        cats.setdefault(cat, []).append(miss)

    in_scope_miss_count = len(cats.get("in_scope_miss", []))
    out_of_scope_count = (len(cats.get("out_of_scope_imaging", []))
                          + len(cats.get("out_of_scope_disorder", [])))
    in_scope_total = total_os - out_of_scope_count
    in_scope_found = in_scope_total - in_scope_miss_count

    lines = [
        "# Original Study Search Validation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Search run: `{search_dir}`",
        "",
        "## Context",
        "",
        "This report validates whether our expanded FND neuroimaging search strategy",
        "recovers the studies included in Boeckle et al. (2016) \"Neural correlates",
        "of conversion disorder: overview and meta-analysis of neuroimaging studies",
        "on motor conversion disorder\" (*BMC Psychiatry*, 16, 195).",
        "",
        "The original study (OS) reported searching Medline, PsycINFO, Psyndex, and",
        "Cochrane to August 2015. Its Table 1 lists 49 included studies.",
        "",
        "## Why literal replication of the OS search is not viable",
        "",
        "We initially attempted to replicate the OS using its published search terms",
        '(`os_validation` mode) and later broadened terms (`os_table_recall` mode).',
        "Neither approach could recover the full Table 1. Investigation revealed",
        "several internal inconsistencies in the OS methodology:",
        "",
        "1. **Database mismatch**: The Methods section names Medline, PsycINFO,",
        "   Psyndex, and Cochrane, but the PRISMA flow includes 784 Scopus records",
        "   from a database never mentioned.",
        "2. **Search terms vs. included studies**: The published search string uses",
        '   only ("dissociative disorder" OR "functional disorder" OR "conversion',
        '   disorder") crossed with neuroimaging terms (MRI, fMRI, PET, VBM). Yet',
        "   Table 1 includes studies on body dysmorphic disorder, somatization",
        "   disorder, dissociative identity disorder, and psychogenic seizures --",
        "   none of which match the published query.",
        "3. **Imaging modality mismatch**: The Methods state eligible modalities are",
        "   PET, MRI, and SPECT, but Table 1 includes studies using EEG (7 studies),",
        "   MEG (1 study), and CT (1 study).",
        "4. **Missing terminology**: Terms like hysteria/hysterical, psychogenic,",
        "   somatoform, PNES, SPECT, and single photon emission appear nowhere in",
        "   the published search string yet are required to find many Table 1 studies.",
        "",
        "These discrepancies suggest that the OS search involved manual/synonym",
        "decisions beyond what the published search string describes, making exact",
        "replication impossible from the reported methodology alone.",
        "",
        "## Our validation approach",
        "",
        "Instead of trying to replicate an unreproducible search, we validated our",
        "own production search strategy by running it with the OS cutoff date:",
        "",
        "- **Search mode**: `full` (expanded FND neuroimaging terms with MeSH,",
        "  language, and publication-type filters)",
        "- **Date range**: inception to 2015/08/31 (matching the OS end date)",
        "- **Databases**: PubMed, Europe PMC, Scopus",
        "  (Web of Science skipped -- no API key)",
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
        "We then matched the deduplicated results against all 49 OS Table 1 studies",
        "by author surname and title/disorder keyword overlap.",
        "",
        f"## Results: {len(found)}/{total_os} studies found",
        "",
        "### Matched studies",
        "",
        "| # | OS study | Disorder | Source DB |",
        "| ---: | --- | --- | --- |",
    ])
    for i, s in enumerate(found, 1):
        rec = s["matched_record"]
        lines.append(
            f"| {i} | {s['study']} | {s['disorder']} | {rec.get('source_db', '')} |"
        )

    lines.extend([
        "",
        f"### Not found ({len(not_found)} studies)",
        "",
        "| OS study | Disorder | Imaging | Miss category |",
        "| --- | --- | --- | --- |",
    ])
    for s in not_found:
        lines.append(
            f"| {s['study']} | {s['disorder']} | {s['imaging']} "
            f"| {CATEGORY_LABELS[s['category']]} |"
        )

    lines.extend([
        "",
        "### Miss analysis",
        "",
    ])
    for cat_key in ["out_of_scope_imaging", "out_of_scope_disorder", "in_scope_miss"]:
        entries = cats.get(cat_key, [])
        lines.append(f"**{CATEGORY_LABELS[cat_key]}** ({len(entries)} studies)")
        lines.append("")
        if not entries:
            lines.append("None.")
            lines.append("")
            continue
        for s in entries:
            lines.append(f"- {s['study']}: {s['disorder']} ({s['imaging']})")
        lines.append("")

    lines.extend([
        "## Conclusion",
        "",
        f"Our search strategy recovers **{in_scope_found}/"
        f"{in_scope_total} in-scope studies** from the OS Table 1",
        f"({in_scope_miss_count} in-scope miss{'es' if in_scope_miss_count != 1 else ''}).",
        "",
        f"The {len(not_found)} unrecovered studies break down as:",
        "",
    ])
    for cat_key in ["out_of_scope_imaging", "out_of_scope_disorder", "in_scope_miss"]:
        entries = cats.get(cat_key, [])
        lines.append(f"- {CATEGORY_LABELS[cat_key]}: {len(entries)}")
    lines.extend([
        "",
        "The vast majority of misses are explainable by being outside the scope",
        "of our FND neuroimaging meta-analysis (wrong imaging modality or wrong",
        "diagnosis). Any remaining in-scope misses are documented above for",
        "investigation; they may reflect papers using unusual terminology or",
        "papers absent from the databases we searched.",
        "",
        f"This validation set (with the {len(found)} matched studies marked as known",
        "includes) is used downstream to test LLM screening pipeline sensitivity.",
        "",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSONL output for LLM pipeline
# ---------------------------------------------------------------------------

def build_screening_jsonl(
    search_records: list[dict[str, Any]],
    found: list[dict],
) -> list[dict[str, Any]]:
    matched_keys = set()
    os_ref_by_key: dict[tuple, str] = {}
    for entry in found:
        rec = entry["matched_record"]
        key = (rec.get("source_db", ""), rec.get("source_id", ""), rec.get("title", ""))
        matched_keys.add(key)
        os_ref_by_key[key] = entry["study"]

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
            "label_source": "os_table_match" if is_match else "search_result",
            "human_gold_decision": "include_candidate" if is_match else None,
            "human_gold_notes": "",
            "os_study_ref": os_ref_by_key.get(key),
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
        description="Validate search recall against Boeckle et al. (2016) Table 1"
    )
    parser.add_argument(
        "--search-dir", type=Path, required=True,
        help="Path to the search run directory (e.g. fnd_search_20260512_154542)",
    )
    parser.add_argument(
        "--os-table", type=Path, default=Path("data/table_of_OS_studies.csv"),
    )
    parser.add_argument(
        "--output-report", type=Path, default=Path("docs/os_validation_report.md"),
    )
    parser.add_argument(
        "--output-jsonl", type=Path, default=Path("data/validation_screening_set.jsonl"),
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

    os_studies = load_os_table(args.os_table)
    search_records = load_search_records(csv_path)

    found, not_found = match_os_studies(os_studies, search_records)

    report = generate_report(
        found, not_found,
        total_os=len(os_studies),
        search_dir=args.search_dir.name,
        per_db=per_db,
        dedup_count=len(search_records),
    )
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report, encoding="utf-8")
    print(f"Wrote validation report -> {args.output_report}")

    screening_items = build_screening_jsonl(search_records, found)
    write_jsonl(screening_items, args.output_jsonl)
    os_count = sum(1 for it in screening_items if it["human_gold_decision"])
    print(f"Wrote {len(screening_items)} records -> {args.output_jsonl}")
    print(f"  {os_count} records marked as known OS includes")
    print(f"  {len(screening_items) - os_count} records with no gold label (screen only)")

    print(f"\nRecall: {len(found)}/{len(os_studies)}")
    cats = {}
    for m in not_found:
        cats.setdefault(m["category"], []).append(m)
    for cat_key in ["out_of_scope_imaging", "out_of_scope_disorder", "in_scope_miss"]:
        entries = cats.get(cat_key, [])
        if entries:
            print(f"  {CATEGORY_LABELS[cat_key]}: {len(entries)}")


if __name__ == "__main__":
    main()
