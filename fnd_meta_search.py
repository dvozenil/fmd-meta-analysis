"""
FND Neuroimaging Meta-Analysis — PRISMA-compliant database search
==================================================================

Updates Boeckle et al. (2016) BMC Psychiatry meta-analysis on motor conversion
disorder, extending to:
  - Current FND terminology (DSM-5: Functional Neurological Symptom Disorder)
  - All FND subtypes (motor, sensory, seizures/PNES, mixed)
  - Both functional AND structural neuroimaging (fMRI, PET, SPECT, VBM, DTI,
    cortical thickness, resting-state, connectivity)

Search modes:
  - "update": 2015 onward (functional track — updating the OS)
  - "full":   inception to present (structural track — no prior meta-analysis)

Databases covered:
  - PubMed (NCBI E-utilities)     — free, API key recommended
  - Europe PMC                    — free, no key needed
  - Web of Science                — requires institutional API key
  - Scopus                        — requires Elsevier API key
  - PsycINFO                      — no REST API; searched manually via OVID/EBSCOhost

Dependencies:
    pip install biopython requests python-dateutil

Repository: https://github.com/dvozenil/fmd-meta-analysis
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests
from Bio import Entrez

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Search mode:
#   "update" — 2015 onward (functional imaging track, updating Boeckle et al.)
#   "full"   — inception to present (structural imaging track, or validation)
SEARCH_MODE = os.getenv("FND_SEARCH_MODE", "update")

SEARCH_START_YEAR: int | None = 2015 if SEARCH_MODE == "update" else None
SEARCH_END_DATE = "2026/04/24"  # YYYY/MM/DD — update to your actual run date

# NCBI credentials (required by NCBI; get a free API key at
# https://www.ncbi.nlm.nih.gov/account/settings/ for 10 req/s vs 3/s)
Entrez.email   = os.getenv("NCBI_EMAIL", "CHANGE_ME@institution.edu")
Entrez.api_key = os.getenv("NCBI_API_KEY")

# Institutional API keys — set as env vars, never hardcode
WOS_API_KEY    = os.getenv("WOS_API_KEY")     # Web of Science Expanded API
SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")  # Elsevier Developer Portal

# Output directory — one folder per run for full auditability
RUN_ID     = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = Path(f"./fnd_search_{RUN_ID}")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(OUTPUT_DIR / "search_log.txt"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RETRY DECORATOR
# ---------------------------------------------------------------------------

def retry(max_attempts: int = 3, backoff_base: float = 2.0,
          retryable_exceptions: tuple = (requests.RequestException, ConnectionError)):
    """Simple exponential-backoff retry for transient API failures."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    wait = backoff_base ** attempt
                    log.warning(f"{func.__name__} attempt {attempt} failed: {exc}. "
                                f"Retrying in {wait:.0f}s...")
                    time.sleep(wait)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# LAYER 1: QUERY CONSTRUCTION
# ---------------------------------------------------------------------------
# Three concept blocks, combined with AND:
#   BLOCK A — FND / conversion disorder terminology (old + new)
#   BLOCK B — Neuroimaging modalities (functional + structural)
#   BLOCK C — Optional filters (human, adult, English, date range)
# ---------------------------------------------------------------------------

# --- Concept A: FND terminology ---------------------------------------------
FND_TERMS = [
    # DSM-5 / ICD-11 preferred
    "functional neurological disorder",
    "functional neurological symptom disorder",
    # DSM-IV / ICD-10
    "conversion disorder",
    "dissociative motor disorder",
    "dissociative convulsion",
    "dissociative convulsions",
    # Functional movement disorder spectrum
    "psychogenic movement disorder",
    "functional movement disorder",
    "functional tremor",
    "psychogenic tremor",
    "functional dystonia",
    "psychogenic dystonia",
    "functional weakness",
    "functional paralysis",
    "functional gait disorder",
    "functional gait",
    # Seizure variants
    "psychogenic non-epileptic seizure",
    "psychogenic nonepileptic seizure",
    "functional seizure",
    "dissociative seizure",
    "pseudoseizure",
    "pseudoseizures",
    "nonepileptic attack disorder",
    # Historical / legacy terms (needed for recall in older literature)
    "hysterical paralysis",
    "hysterical conversion",
    "motor conversion",
    "sensory conversion",
    "astasia-abasia",
]

# --- Concept B: Neuroimaging --------------------------------------------------
IMAGING_TERMS = [
    # General
    "neuroimaging",
    "brain imaging",
    # MRI — functional
    "magnetic resonance imaging",
    "MRI",
    "fMRI",
    "functional MRI",
    "functional magnetic resonance imaging",
    "resting state fMRI",
    "resting-state",
    "functional connectivity",
    # MRI — structural
    "structural MRI",
    "structural magnetic resonance",
    "voxel based morphometry",
    "VBM",
    "cortical thickness",
    "grey matter",
    "gray matter",
    "white matter",
    # Diffusion
    "diffusion tensor imaging",
    "DTI",
    "diffusion weighted imaging",
    "tractography",
    "structural connectivity",
    # Nuclear medicine
    "positron emission tomography",
    "PET",
    "single photon emission",
    "SPECT",
    # Perfusion
    "arterial spin labeling",
    "cerebral blood flow",
    "perfusion",
]


def _date_filter_pubmed() -> str:
    """Build PubMed date filter, or empty string if searching from inception."""
    if SEARCH_START_YEAR is None:
        return ""
    return (f'AND ("{SEARCH_START_YEAR}/01/01"[Date - Publication] : '
            f'"{SEARCH_END_DATE}"[Date - Publication])')


def build_pubmed_query() -> str:
    """PubMed syntax: uses [MeSH Terms], [tiab], field tags."""
    fnd_block = (
        '("Conversion Disorder"[MeSH] OR "Dissociative Disorders"[MeSH] '
        'OR ' + ' OR '.join(f'"{t}"[tiab]' for t in FND_TERMS) + ')'
    )
    imaging_block = (
        '("Neuroimaging"[MeSH] OR "Magnetic Resonance Imaging"[MeSH] '
        'OR "Diffusion Tensor Imaging"[MeSH] OR "Positron-Emission Tomography"[MeSH] '
        'OR "Tomography, Emission-Computed, Single-Photon"[MeSH] '
        'OR ' + ' OR '.join(f'"{t}"[tiab]' for t in IMAGING_TERMS) + ')'
    )
    filters = (
        '(English[Language]) '
        'AND ("humans"[MeSH Terms]) '
        + _date_filter_pubmed()
    )
    exclusions = (
        'NOT ("Editorial"[Publication Type] OR "Letter"[Publication Type] '
        'OR "Comment"[Publication Type])'
    )
    return f"({fnd_block}) AND ({imaging_block}) AND {filters} {exclusions}"


def build_wos_query() -> str:
    """Web of Science syntax: TS= searches Topic (title + abstract + keywords)."""
    fnd  = " OR ".join(f'"{t}"' for t in FND_TERMS)
    imag = " OR ".join(f'"{t}"' for t in IMAGING_TERMS)
    date_part = (f' AND PY={SEARCH_START_YEAR}-{datetime.now().year}'
                 if SEARCH_START_YEAR else "")
    return f'TS=({fnd}) AND TS=({imag}) AND LA=(English){date_part}'


def build_europepmc_query() -> str:
    """Europe PMC syntax: similar to Lucene. Uses TITLE_ABS, PUB_YEAR."""
    fnd  = " OR ".join(f'"{t}"' for t in FND_TERMS)
    imag = " OR ".join(f'"{t}"' for t in IMAGING_TERMS)
    date_part = (f' AND (PUB_YEAR:[{SEARCH_START_YEAR} TO {datetime.now().year}])'
                 if SEARCH_START_YEAR else "")
    return (
        f'(TITLE_ABS:({fnd})) AND (TITLE_ABS:({imag})) '
        f'AND (LANG:"eng"){date_part}'
    )


def build_scopus_query() -> str:
    """Scopus syntax: TITLE-ABS-KEY field tag, AND/OR Boolean."""
    fnd  = " OR ".join(f'"{t}"' for t in FND_TERMS)
    imag = " OR ".join(f'"{t}"' for t in IMAGING_TERMS)
    date_part = (f' AND PUBYEAR > {SEARCH_START_YEAR - 1}'
                 if SEARCH_START_YEAR else "")
    return (
        f'(TITLE-ABS-KEY({fnd})) AND (TITLE-ABS-KEY({imag})){date_part} '
        f'AND LANGUAGE(english)'
    )


# ---------------------------------------------------------------------------
# UNIFIED RECORD SCHEMA
# ---------------------------------------------------------------------------

@dataclass
class Record:
    """Unified schema across all databases."""
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

    def dedup_key(self) -> str:
        """Preferred dedup key: DOI (normalized) > title+year hash."""
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        title_norm = "".join(c.lower() for c in self.title if c.isalnum())[:80]
        return f"tyh:{hashlib.md5(f'{title_norm}_{self.year}'.encode()).hexdigest()}"


# ---------------------------------------------------------------------------
# LAYER 2: DATABASE CLIENTS
# ---------------------------------------------------------------------------

class PubMedClient:
    """NCBI E-utilities via Biopython. Free; 10 req/s with API key, 3/s without."""

    @retry()
    def search(self, query: str, retmax: int = 10000) -> list[Record]:
        log.info(f"PubMed query: {query[:200]}...")
        with Entrez.esearch(db="pubmed", term=query, retmax=retmax,
                            usehistory="y") as h:
            results = Entrez.read(h)
        pmids = results["IdList"]
        webenv, query_key = results["WebEnv"], results["QueryKey"]
        total = int(results["Count"])
        log.info(f"PubMed: {total} hits, retrieving {len(pmids)} records")

        records: list[Record] = []
        batch_size = 200
        for start in range(0, len(pmids), batch_size):
            time.sleep(0.15)
            with Entrez.efetch(db="pubmed", rettype="xml", retmode="xml",
                               retstart=start, retmax=batch_size,
                               webenv=webenv, query_key=query_key) as h:
                xml = h.read()
            records.extend(self._parse_pubmed_xml(xml))
            log.info(f"PubMed: fetched {min(start + batch_size, len(pmids))}/{len(pmids)}")
        return records

    @staticmethod
    def _parse_pubmed_xml(xml_bytes: bytes) -> list[Record]:
        out: list[Record] = []
        root = ET.fromstring(xml_bytes)
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID") or ""
            title = art.findtext(".//ArticleTitle") or ""
            abstract = " ".join(
                (e.text or "") for e in art.findall(".//Abstract/AbstractText")
            ).strip()
            journal = art.findtext(".//Journal/Title") or ""
            year_text = art.findtext(".//PubDate/Year") or ""
            try:
                year = int(year_text) if year_text else None
            except ValueError:
                year = None
            doi = None
            for aid in art.findall(".//ArticleId"):
                if aid.attrib.get("IdType") == "doi":
                    doi = (aid.text or "").strip()
            authors = [
                f"{a.findtext('LastName') or ''} {a.findtext('ForeName') or ''}".strip()
                for a in art.findall(".//Author")
                if a.findtext("LastName")
            ]
            mesh = [m.text for m in art.findall(".//MeshHeading/DescriptorName") if m.text]
            pub_types = [p.text for p in art.findall(".//PublicationType") if p.text]
            keywords = [k.text for k in art.findall(".//Keyword") if k.text]

            out.append(Record(
                source_db="pubmed",
                source_id=pmid,
                doi=doi,
                title=title,
                abstract=abstract,
                authors=authors,
                journal=journal,
                year=year,
                pub_date=year_text,
                keywords=keywords,
                mesh_terms=mesh,
                pub_types=pub_types,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            ))
        return out


class EuropePMCClient:
    """Europe PMC REST API. Free, no auth. Covers PubMed + preprints + patents."""

    BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    @retry()
    def search(self, query: str, page_size: int = 1000) -> list[Record]:
        log.info(f"Europe PMC query: {query[:200]}...")
        records: list[Record] = []
        cursor = "*"
        while True:
            params = {
                "query": query,
                "format": "json",
                "pageSize": page_size,
                "cursorMark": cursor,
                "resultType": "core",
            }
            r = requests.get(self.BASE, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            hits = data.get("resultList", {}).get("result", [])
            if not hits:
                break
            for h in hits:
                records.append(self._parse(h))
            next_cursor = data.get("nextCursorMark")
            log.info(f"Europe PMC: retrieved {len(records)} so far")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(0.2)
        return records

    @staticmethod
    def _parse(h: dict[str, Any]) -> Record:
        year = None
        try:
            year = int(h.get("pubYear", "")) if h.get("pubYear") else None
        except ValueError:
            pass
        return Record(
            source_db="europepmc",
            source_id=h.get("id", ""),
            doi=h.get("doi"),
            title=h.get("title", ""),
            abstract=h.get("abstractText", ""),
            authors=[a.strip() for a in (h.get("authorString") or "").split(",") if a.strip()],
            journal=h.get("journalTitle", ""),
            year=year,
            pub_date=h.get("firstPublicationDate", ""),
            keywords=h.get("keywordList", {}).get("keyword", []) if h.get("keywordList") else [],
            mesh_terms=[m.get("descriptorName", "") for m in
                        (h.get("meshHeadingList", {}) or {}).get("meshHeading", [])],
            pub_types=[p for p in (h.get("pubTypeList", {}) or {}).get("pubType", [])],
            url=f"https://europepmc.org/article/{h.get('source', 'MED')}/{h.get('id', '')}",
        )


class WebOfScienceClient:
    """WoS Expanded API. Requires institutional API key.

    Endpoint doc: https://developer.clarivate.com/apis/wos
    TODO: Verify endpoint URL against current Clarivate docs before first run.
    """

    BASE = "https://wos-api.clarivate.com/api/wos"

    @retry()
    def search(self, query: str, count: int = 100) -> list[Record]:
        if not WOS_API_KEY:
            log.warning("WOS_API_KEY not set — skipping Web of Science")
            return []
        log.info(f"WoS query: {query[:200]}...")
        headers = {"X-ApiKey": WOS_API_KEY, "Accept": "application/json"}
        records: list[Record] = []
        first_record = 1
        while True:
            params = {
                "databaseId": "WOS",
                "usrQuery": query,
                "count": count,
                "firstRecord": first_record,
            }
            r = requests.get(self.BASE, headers=headers, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            hits = data.get("Data", {}).get("Records", {}).get("records", {}).get("REC", [])
            if not hits:
                break
            for h in hits:
                records.append(self._parse(h))
            total = data.get("QueryResult", {}).get("RecordsFound", 0)
            log.info(f"WoS: {len(records)}/{total}")
            first_record += count
            if first_record > total:
                break
            time.sleep(0.5)
        return records

    @staticmethod
    def _parse(rec: dict[str, Any]) -> Record:
        static_data = rec.get("static_data", {})
        summary = static_data.get("summary", {})
        titles = summary.get("titles", {}).get("title", [])
        title_text = next((t.get("content", "") for t in titles
                           if t.get("type") == "item"), "")
        pub_info = summary.get("pub_info", {})
        year = pub_info.get("pubyear")
        doi = None
        for ident in rec.get("dynamic_data", {}).get("cluster_related", {}) \
                      .get("identifiers", {}).get("identifier", []):
            if ident.get("type") == "doi":
                doi = ident.get("value")
        abstract = ""
        for abst in static_data.get("fullrecord_metadata", {}) \
                               .get("abstracts", {}).get("abstract", []):
            abstract += abst.get("abstract_text", {}).get("p", "") + " "
        return Record(
            source_db="wos",
            source_id=rec.get("UID", ""),
            doi=doi,
            title=title_text,
            abstract=abstract.strip(),
            journal=next((t.get("content", "") for t in titles
                          if t.get("type") == "source"), ""),
            year=int(year) if year else None,
            pub_date=str(year) if year else "",
            url=f"https://www.webofscience.com/wos/woscc/full-record/{rec.get('UID', '')}",
        )


class ScopusClient:
    """Elsevier Scopus Search API. Requires API key + institutional access."""

    BASE = "https://api.elsevier.com/content/search/scopus"

    @retry()
    def search(self, query: str, count: int = 100) -> list[Record]:
        if not SCOPUS_API_KEY:
            log.warning("SCOPUS_API_KEY not set — skipping Scopus")
            return []
        log.info(f"Scopus query: {query[:200]}...")
        headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}
        records: list[Record] = []
        start = 0
        while True:
            params = {"query": query, "count": count, "start": start, "view": "COMPLETE"}
            r = requests.get(self.BASE, headers=headers, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            entries = data.get("search-results", {}).get("entry", [])
            if not entries or entries[0].get("error"):
                break
            for e in entries:
                records.append(self._parse(e))
            total = int(data.get("search-results", {}).get("opensearch:totalResults", 0))
            log.info(f"Scopus: {len(records)}/{total}")
            start += count
            if start >= total:
                break
            time.sleep(0.3)
        return records

    @staticmethod
    def _parse(e: dict[str, Any]) -> Record:
        year = None
        cover_date = e.get("prism:coverDate", "")
        if cover_date:
            try:
                year = int(cover_date[:4])
            except ValueError:
                pass
        return Record(
            source_db="scopus",
            source_id=e.get("dc:identifier", "").replace("SCOPUS_ID:", ""),
            doi=e.get("prism:doi"),
            title=e.get("dc:title", ""),
            abstract=e.get("dc:description", ""),
            authors=[a.get("authname", "") for a in e.get("author", []) or []],
            journal=e.get("prism:publicationName", ""),
            year=year,
            pub_date=cover_date,
            keywords=(e.get("authkeywords") or "").split("|"),
            url=next((l.get("@href", "") for l in e.get("link", [])
                      if l.get("@ref") == "scopus"), ""),
        )


# ---------------------------------------------------------------------------
# DEDUPLICATION + EXPORT
# ---------------------------------------------------------------------------

def deduplicate(records: list[Record]) -> tuple[list[Record], dict[str, int]]:
    """Dedup by DOI when available, else by normalized title+year hash.

    First-pass dedup only; Rayyan/ASReview will refine further.
    """
    seen: dict[str, Record] = {}
    dup_sources: dict[str, list[str]] = {}
    for rec in records:
        key = rec.dedup_key()
        if key not in seen:
            seen[key] = rec
            dup_sources[key] = [rec.source_db]
        else:
            dup_sources[key].append(rec.source_db)
    stats = {
        "total_raw": len(records),
        "unique": len(seen),
        "duplicates_removed": len(records) - len(seen),
    }
    return list(seen.values()), stats


def _write_csv(records: list[Record], path: Path) -> None:
    """Write records to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(Record.__dataclass_fields__.keys()))
        w.writeheader()
        for r in records:
            row = asdict(r)
            for k, v in row.items():
                if isinstance(v, list):
                    row[k] = "; ".join(str(x) for x in v)
            w.writerow(row)


def export_results(records: list[Record], all_records_by_db: dict[str, list[Record]],
                   queries: dict[str, str],
                   per_db_counts: dict[str, int], dedup_stats: dict[str, int]) -> None:
    """Writes all PRISMA-required artifacts to OUTPUT_DIR."""

    # 1. Per-database raw CSVs (pre-dedup, for auditability)
    for db_name, db_records in all_records_by_db.items():
        raw_path = OUTPUT_DIR / f"raw_{db_name}.csv"
        _write_csv(db_records, raw_path)
        log.info(f"Wrote {len(db_records)} raw records from {db_name} -> {raw_path}")

    # 2. Deduplicated CSV
    csv_path = OUTPUT_DIR / "records_deduplicated.csv"
    _write_csv(records, csv_path)
    log.info(f"Wrote {len(records)} deduplicated records -> {csv_path}")

    # 3. RIS export for Rayyan / ASReview / Covidence / EndNote
    ris_path = OUTPUT_DIR / "records_deduplicated.ris"
    with open(ris_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write("TY  - JOUR\n")
            f.write(f"TI  - {r.title}\n")
            for a in r.authors:
                f.write(f"AU  - {a}\n")
            if r.year:
                f.write(f"PY  - {r.year}\n")
            if r.journal:
                f.write(f"JO  - {r.journal}\n")
            if r.abstract:
                f.write(f"AB  - {r.abstract}\n")
            if r.doi:
                f.write(f"DO  - {r.doi}\n")
            if r.url:
                f.write(f"UR  - {r.url}\n")
            for kw in r.keywords:
                if kw:
                    f.write(f"KW  - {kw}\n")
            for mh in r.mesh_terms:
                if mh:
                    f.write(f"MH  - {mh}\n")
            f.write(f"DB  - {r.source_db}\n")
            f.write("ER  - \n\n")
    log.info(f"Wrote RIS export -> {ris_path}")

    # 4. PRISMA search metadata
    prisma_meta = {
        "run_id": RUN_ID,
        "search_mode": SEARCH_MODE,
        "search_date": datetime.now(timezone.utc).isoformat(),
        "search_range": (f"{SEARCH_START_YEAR}-01-01 to {SEARCH_END_DATE}"
                         if SEARCH_START_YEAR else f"inception to {SEARCH_END_DATE}"),
        "databases_searched": list(queries.keys()),
        "databases_not_automated": ["PsycINFO (searched manually via OVID/EBSCOhost)"],
        "queries": queries,
        "records_per_database": per_db_counts,
        "deduplication": dedup_stats,
        "filters_applied": {
            "language": "English",
            "subject": "Humans (PubMed only — other DBs filtered at screening)",
            "excluded_pub_types": ["Editorial", "Letter", "Comment"],
        },
        "notes": (
            "Case reports, reviews, and non-primary research are NOT excluded "
            "at search stage per PRISMA 2020 recommendations. They are "
            "excluded during title/abstract screening."
        ),
    }
    meta_path = OUTPUT_DIR / "prisma_search_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(prisma_meta, f, indent=2)
    log.info(f"Wrote PRISMA metadata -> {meta_path}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    log.info(f"Search mode: {SEARCH_MODE}")
    log.info(f"Date range: {'inception' if SEARCH_START_YEAR is None else SEARCH_START_YEAR} "
             f"to {SEARCH_END_DATE}")

    if Entrez.email == "CHANGE_ME@institution.edu":
        log.warning("NCBI_EMAIL not set — update Entrez.email or set NCBI_EMAIL env var")

    queries = {
        "pubmed":    build_pubmed_query(),
        "europepmc": build_europepmc_query(),
        "wos":       build_wos_query(),
        "scopus":    build_scopus_query(),
    }

    with open(OUTPUT_DIR / "queries.json", "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)
    log.info(f"Run ID: {RUN_ID}")
    log.info(f"Output: {OUTPUT_DIR.resolve()}")

    all_records: list[Record] = []
    all_records_by_db: dict[str, list[Record]] = {}
    per_db: dict[str, int] = {}

    clients: dict[str, tuple] = {
        "pubmed":    (PubMedClient(),       queries["pubmed"]),
        "europepmc": (EuropePMCClient(),    queries["europepmc"]),
        "wos":       (WebOfScienceClient(), queries["wos"]),
        "scopus":    (ScopusClient(),       queries["scopus"]),
    }

    for name, (client, q) in clients.items():
        try:
            recs = client.search(q)
            per_db[name] = len(recs)
            all_records_by_db[name] = recs
            all_records.extend(recs)
        except Exception as exc:
            log.exception(f"{name} failed: {exc}")
            per_db[name] = 0
            all_records_by_db[name] = []

    log.info(f"Total raw records across all DBs: {len(all_records)}")
    deduped, dedup_stats = deduplicate(all_records)
    log.info(f"After dedup: {len(deduped)} unique records "
             f"({dedup_stats['duplicates_removed']} duplicates removed)")

    export_results(deduped, all_records_by_db, queries, per_db, dedup_stats)

    log.info("=" * 60)
    log.info("PRISMA flow diagram numbers:")
    for db, n in per_db.items():
        log.info(f"  Records identified from {db}: {n}")
    log.info(f"  Records after duplicates removed: {dedup_stats['unique']}")
    log.info("=" * 60)
    log.info("Next step: import records_deduplicated.ris into Rayyan or ASReview")
    log.info("for title/abstract screening.")


if __name__ == "__main__":
    main()
