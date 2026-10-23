#!/usr/bin/env python3
"""Post-dedup same-title sweep: flag residual same-title duplicate candidates.

Rationale: the production ASySD-class dedup let a small number of true
duplicate pairs leak into a frozen corpus (13 pairs in the
2026-07-31 screening corpus). This sweep is a read-only safety net: it groups
records by normalized title and emits *candidate* pairs for human review into
a maybe-pairs CSV. It never modifies the input file or any pipeline state.

Classification of each candidate pair (record r1, r2 with equal normalized
titles):
  - TRUE_DUP_CANDIDATE if ANY of:
      * both DOIs present and equal (same-work records; includes
        erratum/corrigendum pairs, which share their article's DOI — the
        adjudicator decides whether to keep both),
      * abstract Jaro-Winkler similarity >= 0.90 (rapidfuzz, first 2000
        chars),
      * both DOIs ABSENT and same year and author last-name overlap.
  - PREPRINT_CANDIDATE if exactly one DOI starts with 10.1101/ or 10.64898/
    and titles match (preprint vs published version of the same work).
  - DISTINCT: not written to the output.

Missing/empty DOIs are treated as UNKNOWN, never as equal — generic-title
works (e.g. distinct encyclopedia chapters titled "Conversion disorder.")
with two missing DOIs must NOT merge on title alone; the missing-DOI rule
requires year + author-last-name overlap on top.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

try:
    from rapidfuzz.distance import JaroWinkler
except ImportError:  # pragma: no cover - rapidfuzz is a project dependency
    JaroWinkler = None

ABSTRACT_SIM_THRESHOLD = 0.90
ABSTRACT_SLICE = 2000
PREPRINT_DOI_PREFIXES = ("10.1101/", "10.64898/")

# Output columns
OUTPUT_COLUMNS = [
    "record_id1", "source_db1", "title1", "doi1", "year1",
    "record_id2", "source_db2", "title2", "doi2", "year2",
    "title_norm", "abstract_sim", "class", "same_doi",
]

_CLASS_TRUE_DUP = "TRUE_DUP_CANDIDATE"
_CLASS_PREPRINT = "PREPRINT_CANDIDATE"


def normalize_title(title: str) -> str:
    """Normalize a title for grouping: lowercase, strip punctuation, collapse whitespace."""
    s = (title or "").lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _read_records(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _author_last_names(authors_field: str) -> set[str]:
    """Extract last names from a free-form authors string.

    Handles the production formats: 'Last, First; ...' (wos/psycinfo),
    'Last F.M.; ...' (scopus/pubmed), 'Last F.; ...' (europepmc).
    """
    s = (authors_field or "").strip()
    if not s:
        return set()
    names = []
    for chunk in re.split(r"[;|]", s):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:
            last = chunk.split(",", 1)[0]
        else:
            last = chunk.split()[0]
        last = last.strip(" .").lower()
        # ASCII-fold accented characters so 'Müller' ~ 'muler' ~ 'miller'-class matches
        try:
            import unicodedata
            last = "".join(c for c in unicodedata.normalize("NFKD", last)
                           if not unicodedata.combining(c))
        except Exception:
            pass
        if last:
            names.append(last)
    return set(names)


def _classify(r1: dict, r2: dict, abstract_sim: float) -> str | None:
    """Classify a same-title candidate pair. Returns None for DISTINCT.

    Precedence: identical DOIs -> TRUE_DUP; one preprint DOI -> PREPRINT;
    then the abstract-similarity rule (applies regardless of DOI state —
    this is what catches cross-DB pairs where one side carries a Figshare
    deposit DOI or a concatenated multi-DOI string); then the missing-DOI
    corroboration rule.
    """
    doi1 = (r1.get("doi") or "").strip()
    doi2 = (r2.get("doi") or "").strip()

    if doi1 and doi2:
        if doi1 == doi2:
            return _CLASS_TRUE_DUP
        if doi1.startswith(PREPRINT_DOI_PREFIXES) != doi2.startswith(PREPRINT_DOI_PREFIXES):
            return _CLASS_PREPRINT
        # Both present but different: still same-work candidates when the
        # abstracts are near-identical (e.g. one side has a wrong/deposit DOI).
        return _CLASS_TRUE_DUP if abstract_sim >= ABSTRACT_SIM_THRESHOLD else None

    # Exactly one DOI present (the other missing/unknown): only the
    # abstract-similarity signal can justify a flag.
    if abstract_sim >= ABSTRACT_SIM_THRESHOLD:
        return _CLASS_TRUE_DUP

    # Both DOIs ABSENT (UNKNOWN, never equal): require strong corroboration.
    if not doi1 and not doi2:
        y1, y2 = (r1.get("year") or "").strip(), (r2.get("year") or "").strip()
        same_year = y1 and y1 == y2
        a1 = _author_last_names(r1.get("authors") or "")
        a2 = _author_last_names(r2.get("authors") or "")
        if same_year and a1 & a2:
            return _CLASS_TRUE_DUP
    return None


def _abstract_sim(r1: dict, r2: dict) -> float:
    a1 = (r1.get("abstract") or "").strip()[:ABSTRACT_SLICE]
    a2 = (r2.get("abstract") or "").strip()[:ABSTRACT_SLICE]
    if not a1 or not a2:
        return 0.0
    if JaroWinkler is None:
        raise SystemExit("rapidfuzz is required for the same-title sweep")
    return JaroWinkler.normalized_similarity(a1, a2)


def sweep(records: list[dict]) -> list[dict]:
    """Group by normalized title and classify candidate pairs. Read-only."""
    groups: dict[str, list[dict]] = {}
    for r in records:
        tnorm = normalize_title(r.get("title") or "")
        if tnorm:
            groups.setdefault(tnorm, []).append(r)

    pairs: list[dict] = []
    for tnorm, members in groups.items():
        if len(members) < 2:
            continue
        # Deterministic order: sort by (source_db, source_id) before pairing.
        members = sorted(members, key=lambda r: (r.get("source_db") or "", r.get("source_id") or ""))
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                r1, r2 = members[i], members[j]
                sim = _abstract_sim(r1, r2)
                cls = _classify(r1, r2, sim)
                if cls is None:
                    continue
                doi1 = (r1.get("doi") or "").strip()
                doi2 = (r2.get("doi") or "").strip()
                pairs.append({
                    "record_id1": r1.get("source_id") or "",
                    "source_db1": r1.get("source_db") or "",
                    "title1": r1.get("title") or "",
                    "doi1": doi1,
                    "year1": r1.get("year") or "",
                    "record_id2": r2.get("source_id") or "",
                    "source_db2": r2.get("source_db") or "",
                    "title2": r2.get("title") or "",
                    "doi2": doi2,
                    "year2": r2.get("year") or "",
                    "title_norm": tnorm,
                    "abstract_sim": f"{sim:.4f}",
                    "class": cls,
                    "same_doi": "1" if (doi1 and doi1 == doi2) else "0",
                })
    return pairs


def run_sweep(input_csv: Path, output_csv: Path) -> list[dict]:
    """Read records CSV, sweep, write output CSV. Returns the pairs written."""
    records = _read_records(input_csv)
    pairs = sweep(records)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for p in pairs:
            writer.writerow(p)

    n_true = sum(1 for p in pairs if p["class"] == _CLASS_TRUE_DUP)
    n_pre = sum(1 for p in pairs if p["class"] == _CLASS_PREPRINT)
    n_same_doi = sum(1 for p in pairs if p["same_doi"] == "1")
    print(f"Read {len(records)} records from {input_csv}")
    print(f"Same-title candidate pairs: {len(pairs)} "
          f"({n_true} { _CLASS_TRUE_DUP}, {n_pre} { _CLASS_PREPRINT}; "
          f"{n_same_doi} with identical DOIs)")
    print(f"Wrote {output_csv}")
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-dedup same-title sweep: flag residual duplicate candidates.")
    parser.add_argument("--input", required=True, type=Path,
                        help="Records CSV (schema as records_deduplicated.csv)")
    parser.add_argument("--output", type=Path, default=Path("maybe_pairs_title_sweep.csv"),
                        help="Output maybe-pairs CSV (default: maybe_pairs_title_sweep.csv)")
    args = parser.parse_args(argv)

    if not args.input.is_file():
        parser.error(f"input CSV not found: {args.input}")

    run_sweep(args.input, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
