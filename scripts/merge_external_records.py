#!/usr/bin/env python3
"""Merge manual database exports into an existing search run before dedup.

This is intended for Web of Science / PsycINFO / other manual exports when API
access is unavailable or incomplete. It reads the canonical ``raw_*.csv`` files
from a ``fnd_search_*`` directory, normalizes external CSV exports into the same
record schema, deduplicates the combined pool, and writes a final merged output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


log = logging.getLogger(__name__)


@dataclass
class Record:
    source_db: str
    source_id: str
    doi: str | None = None
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: int | None = None
    pub_date: str = ""
    keywords: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    pub_types: list[str] = field(default_factory=list)
    url: str = ""
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def _title_year_key(self) -> str:
        title_norm = "".join(c.lower() for c in self.title if c.isalnum())[:80]
        return f"tyh:{hashlib.md5(f'{title_norm}_{self.year}'.encode()).hexdigest()}"

    def dedup_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        return self._title_year_key()


def _first(row: dict[str, str], names: list[str]) -> str:
    normalized = {k.strip().lower(): v for k, v in row.items() if k is not None}
    for name in names:
        value = normalized.get(name.lower())
        if value:
            return value.strip()
    return ""


def _split_list(value: str) -> list[str]:
    if not value:
        return []
    separators = ["; ", ";", "|"]
    parts = [value]
    for sep in separators:
        if sep in value:
            parts = value.split(sep)
            break
    return [p.strip() for p in parts if p.strip()]


def _parse_year(value: str) -> int | None:
    for token in value.replace("/", "-").split("-"):
        if len(token) == 4 and token.isdigit():
            return int(token)
    if value.isdigit() and len(value) == 4:
        return int(value)
    return None


def read_canonical_csv(path: Path) -> list[Record]:
    records: list[Record] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(
                Record(
                    source_db=row.get("source_db", path.stem.removeprefix("raw_")),
                    source_id=row.get("source_id", ""),
                    doi=row.get("doi") or None,
                    title=row.get("title", ""),
                    abstract=row.get("abstract", ""),
                    authors=_split_list(row.get("authors", "")),
                    journal=row.get("journal", ""),
                    year=_parse_year(row.get("year", "")),
                    pub_date=row.get("pub_date", ""),
                    keywords=_split_list(row.get("keywords", "")),
                    mesh_terms=_split_list(row.get("mesh_terms", "")),
                    pub_types=_split_list(row.get("pub_types", "")),
                    url=row.get("url", ""),
                    retrieved_at=row.get("retrieved_at")
                    or datetime.now(timezone.utc).isoformat(),
                )
            )
    return records


def read_external_csv(path: Path, source_db: str) -> list[Record]:
    """Read flexible CSV exports from WoS/PsycINFO/EndNote-like sources."""
    records: list[Record] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for idx, row in enumerate(csv.DictReader(f), start=1):
            title = _first(row, ["title", "article title", "document title", "TI"])
            pub_date = _first(
                row,
                ["pub_date", "publication date", "date", "published", "early access date"],
            )
            year = _parse_year(_first(row, ["year", "publication year", "PY"]) or pub_date)
            source_id = _first(
                row,
                [
                    "source_id",
                    "accession number",
                    "ut (unique wos id)",
                    "unique wos id",
                    "wos accession number",
                    "record number",
                    "id",
                ],
            )
            if not source_id:
                source_id = f"{source_db}:external:{idx}"

            keywords = []
            for col in [
                "keywords",
                "author keywords",
                "keywords plus",
                "mesh_terms",
                "MeSH Terms",
            ]:
                keywords.extend(_split_list(_first(row, [col])))

            records.append(
                Record(
                    source_db=source_db,
                    source_id=source_id,
                    doi=_first(row, ["doi", "DOI"]) or None,
                    title=title,
                    abstract=_first(row, ["abstract", "abstract note", "AB"]),
                    authors=_split_list(_first(row, ["authors", "author full names", "AU"])),
                    journal=_first(row, ["journal", "source title", "publication title", "SO"]),
                    year=year,
                    pub_date=pub_date,
                    keywords=keywords,
                    url=_first(row, ["url", "link", "URL"]),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            )
    return records


def _words(title: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in title).split()
            if len(w) > 2}


def _titles_similar(title_a: str, title_b: str, threshold: float = 0.4) -> bool:
    w1, w2 = _words(title_a), _words(title_b)
    if not w1 or not w2:
        return True
    return len(w1 & w2) / len(w1 | w2) >= threshold


def deduplicate(records: list[Record]) -> tuple[list[Record], dict[str, int]]:
    seen: dict[str, Record] = {}
    dup_sources: dict[str, list[str]] = {}
    doi_collisions: list[tuple[Record, Record]] = []

    for rec in records:
        key = rec.dedup_key()
        if key not in seen:
            seen[key] = rec
            dup_sources[key] = [rec.source_db]
        elif key.startswith("doi:"):
            existing = seen[key]
            if not _titles_similar(existing.title, rec.title):
                fallback = rec._title_year_key()
                if fallback not in seen:
                    seen[fallback] = rec
                    dup_sources[fallback] = [rec.source_db]
                    doi_collisions.append((existing, rec))
                else:
                    dup_sources[fallback].append(rec.source_db)
            else:
                dup_sources[key].append(rec.source_db)
        else:
            dup_sources[key].append(rec.source_db)

    return list(seen.values()), {
        "total_raw": len(records),
        "unique": len(seen),
        "duplicates_removed": len(records) - len(seen),
        "doi_collisions_rescued": len(doi_collisions),
    }


def write_csv(records: list[Record], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(Record.__dataclass_fields__.keys()))
        writer.writeheader()
        for record in records:
            row = asdict(record)
            for key, value in row.items():
                if isinstance(value, list):
                    row[key] = "; ".join(str(v) for v in value)
            writer.writerow(row)


def write_ris(records: list[Record], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write("TY  - JOUR\n")
            f.write(f"TI  - {record.title}\n")
            for author in record.authors:
                f.write(f"AU  - {author}\n")
            if record.year:
                f.write(f"PY  - {record.year}\n")
            if record.journal:
                f.write(f"JO  - {record.journal}\n")
            if record.abstract:
                f.write(f"AB  - {record.abstract}\n")
            if record.doi:
                f.write(f"DO  - {record.doi}\n")
            if record.url:
                f.write(f"UR  - {record.url}\n")
            for keyword in record.keywords:
                f.write(f"KW  - {keyword}\n")
            f.write(f"DB  - {record.source_db}\n")
            f.write("ER  - \n\n")


def parse_external_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "External CSV must use source_db=path, e.g. wos=exports/wos.csv"
        )
    source_db, path = value.split("=", 1)
    source_db = source_db.strip().lower()
    if not source_db:
        raise argparse.ArgumentTypeError("source_db cannot be empty")
    return source_db, Path(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge manual CSV exports into a fnd_search_* run and deduplicate."
    )
    parser.add_argument("--search-dir", required=True, type=Path)
    parser.add_argument(
        "--external-csv",
        action="append",
        default=[],
        type=parse_external_arg,
        metavar="SOURCE=PATH",
        help="External CSV export to merge. Repeat for multiple databases.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Destination directory. Defaults to <search-dir>/merged_external.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    args = parse_args()
    search_dir = args.search_dir
    output_dir = args.output_dir or search_dir / "merged_external"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[Record] = []
    records_by_db: dict[str, list[Record]] = {}

    for raw_path in sorted(search_dir.glob("raw_*.csv")):
        db_name = raw_path.stem.removeprefix("raw_")
        records = read_canonical_csv(raw_path)
        records_by_db[db_name] = records
        all_records.extend(records)
        write_csv(records, output_dir / f"raw_{db_name}.csv")
        log.info("Loaded %s records from %s", len(records), raw_path)

    for source_db, path in args.external_csv:
        records = read_external_csv(path, source_db)
        records_by_db[source_db] = records_by_db.get(source_db, []) + records
        all_records.extend(records)
        write_csv(records_by_db[source_db], output_dir / f"raw_{source_db}.csv")
        log.info("Loaded %s external records from %s as %s", len(records), path, source_db)

    deduped, dedup_stats = deduplicate(all_records)
    write_csv(deduped, output_dir / "records_deduplicated.csv")
    write_ris(deduped, output_dir / "records_deduplicated.ris")

    queries = {}
    queries_path = search_dir / "queries.json"
    if queries_path.exists():
        queries = json.loads(queries_path.read_text(encoding="utf-8"))

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_search_dir": str(search_dir),
        "external_csv": [
            {"source_db": source_db, "path": str(path)}
            for source_db, path in args.external_csv
        ],
        "queries": queries,
        "records_per_database": {
            db_name: len(records) for db_name, records in sorted(records_by_db.items())
        },
        "deduplication": dedup_stats,
        "notes": (
            "Merged output includes API raw records plus manually exported CSV "
            "records normalized before deduplication."
        ),
    }
    (output_dir / "merge_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    log.info("Wrote merged deduplicated CSV/RIS to %s", output_dir)
    log.info(
        "Deduplication: %s raw -> %s unique (%s removed)",
        dedup_stats["total_raw"],
        dedup_stats["unique"],
        dedup_stats["duplicates_removed"],
    )


if __name__ == "__main__":
    main()
