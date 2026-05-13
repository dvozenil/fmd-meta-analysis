#!/usr/bin/env python3
"""Resolve Boeckle et al. (2016) Table 1 reference numbers to full citations.

Fetches the structured reference list from CrossRef (DOI 10.1186/s12888-016-0890-x),
maps each [N] in data/table_of_OS_studies.csv to its DOI / title / year, and writes
data/table_of_OS_studies_resolved.csv.

Falls back to parsing the PDF at docs/references/s12888-016-0890-x.pdf if CrossRef
is unavailable.

Usage:
    python scripts/resolve_os_references.py
    python scripts/resolve_os_references.py --from-pdf   # force PDF fallback
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BOECKLE_DOI = "10.1186/s12888-016-0890-x"
CROSSREF_URL = f"https://api.crossref.org/works/{BOECKLE_DOI}"
OS_TABLE_PATH = Path("data/table_of_OS_studies.csv")
OUTPUT_PATH = Path("data/table_of_OS_studies_resolved.csv")
PDF_PATH = Path("docs/references/s12888-016-0890-x.pdf")
CACHE_PATH = Path("data/boeckle_2016_references_crossref.json")


def fetch_crossref_references() -> list[dict[str, Any]]:
    import requests

    if CACHE_PATH.exists():
        print(f"Using cached CrossRef data from {CACHE_PATH}")
        with open(CACHE_PATH) as f:
            return json.load(f)

    print(f"Fetching references from CrossRef for DOI {BOECKLE_DOI} ...")
    resp = requests.get(
        CROSSREF_URL,
        headers={"User-Agent": "FMD-meta-search/1.0 (mailto:research@example.com)"},
        timeout=30,
    )
    resp.raise_for_status()
    refs = resp.json()["message"]["reference"]

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)
    print(f"  Cached {len(refs)} references to {CACHE_PATH}")
    return refs


def parse_pdf_references() -> list[dict[str, Any]]:
    """Fallback: extract references from the PDF using pdftotext."""
    if not PDF_PATH.exists():
        print(f"PDF not found at {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["pdftotext", "-layout", str(PDF_PATH), "-"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"pdftotext failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    text = result.stdout
    ref_section = text[text.rfind("\nReferences\n"):]
    refs: list[dict[str, Any]] = []
    for m in re.finditer(
        r"^\s*(\d{1,3})\.\s+(.+?)(?=\n\s*\d{1,3}\.\s|\Z)",
        ref_section,
        re.MULTILINE | re.DOTALL,
    ):
        num = int(m.group(1))
        raw = " ".join(m.group(2).split())
        doi_match = re.search(r"(10\.\d{4,}/[^\s]+)", raw)
        refs.append({
            "key": f"pdf_{num}",
            "unstructured": raw,
            "DOI": doi_match.group(1).rstrip(".") if doi_match else None,
        })
    while len(refs) < 110:
        refs.append({})
    return refs


def load_os_table() -> list[dict[str, str]]:
    with open(OS_TABLE_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        study = row["Study"].strip().strip('"')
        m = re.search(r"\[(\d+)\]", study)
        out.append({
            "study": study,
            "ref_number": m.group(1) if m else "",
            "disorder": row["Disorder"].strip(),
            "control_group": row["Control group"].strip(),
            "n_participants": row["Number of participants"].strip(),
            "imaging": row["Imaging method"].strip(),
        })
    return out


def resolve(os_rows: list[dict], refs: list[dict]) -> list[dict]:
    """Attach ref_doi, ref_year, ref_unstructured to each OS row."""
    for row in os_rows:
        n = int(row["ref_number"]) if row["ref_number"] else 0
        if n < 1 or n > len(refs):
            row.update({"ref_doi": "", "ref_year": "", "ref_unstructured": ""})
            continue
        ref = refs[n - 1]
        row["ref_doi"] = ref.get("DOI", "") or ""
        row["ref_year"] = ref.get("year", "") or ""
        raw = ref.get("unstructured", "") or ""
        if not row["ref_year"] and raw:
            ym = re.search(r"\b(19|20)\d{2}\b", raw)
            if ym:
                row["ref_year"] = ym.group(0)
        row["ref_unstructured"] = raw
    return os_rows


def write_resolved(rows: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "study", "ref_number", "ref_doi", "ref_year",
        "disorder", "control_group", "n_participants", "imaging",
        "ref_unstructured",
    ]
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-pdf", action="store_true",
                        help="Force PDF fallback instead of CrossRef")
    args = parser.parse_args()

    os_rows = load_os_table()

    if args.from_pdf:
        refs = parse_pdf_references()
    else:
        try:
            refs = fetch_crossref_references()
        except Exception as exc:
            print(f"CrossRef fetch failed ({exc}); falling back to PDF")
            refs = parse_pdf_references()

    print(f"Loaded {len(os_rows)} OS table rows, {len(refs)} references")

    has_doi = sum(1 for row in os_rows if refs[int(row["ref_number"]) - 1].get("DOI")
                  for _ in [None] if row["ref_number"])
    print(f"References with DOI: {has_doi}/{len(os_rows)}")

    resolved = resolve(os_rows, refs)
    write_resolved(resolved)

    no_doi = [r for r in resolved if not r["ref_doi"]]
    if no_doi:
        print(f"\nWarning: {len(no_doi)} rows without DOI:")
        for r in no_doi:
            print(f"  {r['study']}")


if __name__ == "__main__":
    main()
