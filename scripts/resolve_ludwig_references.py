#!/usr/bin/env python3
"""Resolve Ludwig et al. (2018) included studies to DOIs via CrossRef.

Fetches the structured reference list from CrossRef for the Ludwig paper
(DOI 10.1016/S2215-0366(18)30051-8), matches each entry in
data/ludwig_included_studies.csv to its DOI, and writes
data/ludwig_included_studies_resolved.csv.

Falls back to querying CrossRef works API per-study when the reference list
does not provide a DOI (common for older Elsevier papers).

Usage:
    python scripts/resolve_ludwig_references.py
    python scripts/resolve_ludwig_references.py --no-cache
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

LUDWIG_DOI = "10.1016/S2215-0366(18)30051-8"
CROSSREF_REFS_URL = f"https://api.crossref.org/works/{LUDWIG_DOI}"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"
HEADERS = {"User-Agent": "FMD-meta-search/1.0 (mailto:research@example.com)"}

INPUT_PATH = Path("data/ludwig_included_studies.csv")
OUTPUT_PATH = Path("data/ludwig_included_studies_resolved.csv")
CACHE_PATH = Path("data/ludwig_2018_references_crossref.json")


def fetch_crossref_references(use_cache: bool = True) -> list[dict[str, Any]]:
    if use_cache and CACHE_PATH.exists():
        print(f"Using cached CrossRef data from {CACHE_PATH}")
        with open(CACHE_PATH) as f:
            return json.load(f)

    print(f"Fetching references from CrossRef for DOI {LUDWIG_DOI} ...")
    resp = requests.get(CROSSREF_REFS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    refs = resp.json()["message"].get("reference", [])

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)
    print(f"  Cached {len(refs)} references to {CACHE_PATH}")
    return refs


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _title_words(title: str) -> set[str]:
    return {w for w in _normalize_title(title).split() if len(w) >= 3}


def _title_jaccard(a: str, b: str) -> float:
    wa, wb = _title_words(a), _title_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _extract_year(text: str) -> str:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return m.group(0) if m else ""


def _query_crossref_for_study(
    first_author: str, title: str, year: str
) -> str | None:
    """Query CrossRef works API for a single study to find its DOI."""
    query = f"{first_author} {title[:80]}"
    params = {
        "query": query,
        "rows": 5,
        "filter": f"from-pub-date:{int(year) - 1},until-pub-date:{int(year) + 1}" if year else "",
    }
    if not params["filter"]:
        del params["filter"]
    try:
        resp = requests.get(
            CROSSREF_WORKS_URL,
            params=params,
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
    except Exception as exc:
        print(f"  CrossRef query failed for {first_author} {year}: {exc}")
        return None

    for item in items:
        candidate_title = " ".join(item.get("title", []))
        if _title_jaccard(candidate_title, title) >= 0.5:
            return item.get("DOI")
    return None


def load_studies() -> list[dict[str, str]]:
    with open(INPUT_PATH, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def match_ref_to_study(
    ref: dict[str, Any], study: dict[str, str]
) -> bool:
    """Check if a CrossRef reference entry matches a study row."""
    ref_text = ref.get("unstructured", "") or ""
    ref_doi = ref.get("DOI", "") or ""

    surname = study["first_author"].lower()
    if surname and surname in ref_text.lower():
        year = study["year"]
        if year and year in ref_text:
            return True

    if ref_doi:
        ref_title_parts = ref.get("article-title", "") or ""
        if ref_title_parts and _title_jaccard(ref_title_parts, study["title"]) >= 0.4:
            return True

    return False


def resolve(
    studies: list[dict[str, str]],
    refs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Attach ref_doi and ref_year to each study row."""
    unresolved_count = 0

    for study in studies:
        ref_numbers = [n.strip() for n in study["ref_number"].split(";")]
        primary_ref_num = int(ref_numbers[0]) if ref_numbers[0] else 0

        doi_found = ""
        # Try direct index lookup first (ref_number maps to position in reference list)
        if primary_ref_num > 0 and primary_ref_num <= len(refs):
            ref = refs[primary_ref_num - 1]
            if match_ref_to_study(ref, study):
                doi_found = ref.get("DOI", "") or ""

        # If direct lookup failed, scan all refs for a match
        if not doi_found:
            for ref in refs:
                if match_ref_to_study(ref, study):
                    doi_found = ref.get("DOI", "") or ""
                    if doi_found:
                        break

        study["ref_doi"] = doi_found
        study["ref_year"] = study["year"]

        if not doi_found:
            unresolved_count += 1

    print(f"Resolved {len(studies) - unresolved_count}/{len(studies)} DOIs from reference list")
    return studies


def resolve_missing_via_works_api(studies: list[dict[str, str]]) -> int:
    """Query CrossRef works API for studies still missing DOIs."""
    missing = [s for s in studies if not s.get("ref_doi")]
    if not missing:
        return 0

    print(f"Querying CrossRef works API for {len(missing)} unresolved studies...")
    resolved = 0
    for i, study in enumerate(missing, 1):
        doi = _query_crossref_for_study(
            study["first_author"], study["title"], study["year"]
        )
        if doi:
            study["ref_doi"] = doi
            resolved += 1
            print(f"  [{i}/{len(missing)}] Found: {study['first_author']} {study['year']} -> {doi}")
        else:
            print(f"  [{i}/{len(missing)}] Not found: {study['first_author']} {study['year']}")
        time.sleep(0.5)

    return resolved


def write_resolved(studies: list[dict[str, str]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "ref_number", "first_author", "year", "ref_doi", "ref_year",
        "title", "journal", "symptom_type", "n_fnd", "n_control",
        "ref_unstructured",
    ]
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(studies)
    print(f"Wrote {len(studies)} rows to {OUTPUT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve Ludwig et al. (2018) included studies to DOIs"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Force fresh CrossRef fetch (ignore cache)",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        print(f"Input file not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    studies = load_studies()
    print(f"Loaded {len(studies)} studies from {INPUT_PATH}")

    refs = fetch_crossref_references(use_cache=not args.no_cache)
    print(f"Loaded {len(refs)} references from CrossRef")

    resolve(studies, refs)

    extra = resolve_missing_via_works_api(studies)
    if extra:
        print(f"Resolved {extra} additional DOIs via works API")

    write_resolved(studies)

    no_doi = [s for s in studies if not s["ref_doi"]]
    if no_doi:
        print(f"\nWarning: {len(no_doi)} studies still without DOI:")
        for s in no_doi:
            print(f"  {s['first_author']} ({s['year']}): {s['title'][:60]}")
    else:
        print("\nAll studies resolved to DOIs.")


if __name__ == "__main__":
    main()
