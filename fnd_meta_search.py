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
  - "os_validation": inception to August 2015 using terms matched as closely
    as practical to Boeckle et al. (2016), for validation only
  - "os_table_recall": inception to August 2015 with broadened terms
    (no language filter at search stage) to maximise recovery of the 49
    studies in Boeckle et al. Table 1

Databases covered:
  - PubMed (NCBI E-utilities)     — free, API key recommended
  - Europe PMC                    — free, no key needed
  - Web of Science                — requires institutional API key
  - Scopus                        — requires Elsevier API key
  - PsycINFO                      — no REST API; searched manually via OVID/EBSCOhost

Dependencies:
    pip install biopython requests python-dotenv

Repository: https://github.com/dvozenil/fmd-meta-analysis
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import requests
from Bio import Entrez

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv(Path(__file__).with_name(".env"))

try:
    from dedup_asysd import deduplicate_asysd
except ImportError:
    deduplicate_asysd = None

# ---------------------------------------------------------------------------
# CLI ARGUMENT PARSING
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FND Neuroimaging Meta-Analysis — PRISMA-compliant database search"
    )
    parser.add_argument(
        "--mode", choices=["update", "full", "os_validation", "os_table_recall",
                           "ludwig_validation"],
        default=None,
        help="Search mode (overrides FND_SEARCH_MODE env var)",
    )
    parser.add_argument("--update", action="store_const", const="update", dest="mode")
    parser.add_argument("--full", action="store_const", const="full", dest="mode")
    parser.add_argument("--os_validation", action="store_const", const="os_validation", dest="mode")
    parser.add_argument("--os_table_recall", action="store_const", const="os_table_recall", dest="mode")
    parser.add_argument("--ludwig_validation", action="store_const", const="ludwig_validation", dest="mode")
    parser.add_argument(
        "--auto", action="store_true",
        help="Run all steps without interactive confirmation prompts",
    )
    parser.add_argument(
        "--dedup", choices=["asysd", "simple"], default="asysd",
        help="Deduplication algorithm: 'asysd' (ASySD-class, default) or "
             "'simple' (old DOI+title hash dedup)",
    )
    return parser.parse_args()

_cli_args = _parse_args()
AUTO_MODE = _cli_args.auto
DEDUP_METHOD = _cli_args.dedup

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

# Search mode:
#   "update"          — 2015 onward (functional imaging track, updating Boeckle)
#   "full"            — inception to present (structural imaging track)
#   "os_validation"   — inception to August 2015 using original-study terms
#   "os_table_recall" — inception to August 2015, broadened terms, no language filter
SEARCH_MODE = _cli_args.mode or os.getenv("FND_SEARCH_MODE", "update")
VALID_SEARCH_MODES = {"update", "full", "os_validation", "os_table_recall",
                      "ludwig_validation"}
_VALIDATION_MODES = {"os_validation", "os_table_recall", "ludwig_validation"}
if SEARCH_MODE not in VALID_SEARCH_MODES:
    raise ValueError(
        f"Unknown FND_SEARCH_MODE={SEARCH_MODE!r}; expected one of "
        f"{sorted(VALID_SEARCH_MODES)}"
    )

SEARCH_START_YEAR: int | None = 2015 if SEARCH_MODE == "update" else None
_VALIDATION_END_DATES = {
    "os_validation": "2015/08/31",
    "os_table_recall": "2015/08/31",
    "ludwig_validation": "2016/11/04",
}
DEFAULT_SEARCH_END_DATE = (
    _VALIDATION_END_DATES.get(SEARCH_MODE, datetime.now().strftime("%Y/%m/%d"))
)
SEARCH_END_DATE = os.getenv("FND_SEARCH_END_DATE", DEFAULT_SEARCH_END_DATE)

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

# Original-study validation terms. Boeckle et al. (2016) report searching
# Medline, PsycINFO, Psyndex, and Cochrane to August 2015 with these concept
# blocks. Database syntax is adapted here for the APIs this script can query.
OS_FND_TERMS = [
    "dissociative disorder",
    "functional disorder",
    "conversion disorder",
]

OS_IMAGING_TERMS = [
    "neuro imaging",
    "magnetic resonance imaging",
    "fMRI",
    "MRI",
    "VBM",
    "PET",
]

# Broadened terms for reproducing the 49-study Table 1 from Boeckle et al.
# The published search string is narrower than what Table 1 actually contains
# (e.g. SPECT, EEG, MEG, CT, hysteria, psychogenic, somatoform, body
# dysmorphic, and PNES studies all appear in the table but not in the query).
OS_RECALL_FND_TERMS = [
    # Original OS terms
    "dissociative disorder",
    "functional disorder",
    "conversion disorder",
    # Historical / legacy (compound phrases — bare "hysteria"/"hysterical" too broad)
    "hysterical conversion",
    "hysterical paralysis",
    "hysterical anaesthesia",
    "motor conversion",
    "sensory conversion",
    "sensorimotor conversion",
    # Psychogenic spectrum (compound phrases — bare "psychogenic" too broad)
    "psychogenic movement disorder",
    "psychogenic non-epileptic seizure",
    "psychogenic nonepileptic seizure",
    "psychogenic tremor",
    "psychogenic dystonia",
    "psychogenic paralysis",
    # Somatoform (as phrase — bare "somatoform" too broad)
    "somatoform disorder",
    "somatization disorder",
    # Body dysmorphic
    "body dysmorphic disorder",
    # Seizure variants
    "PNES",
    "non-epileptic seizure",
    "nonepileptic seizure",
    "non-epileptic attack",
    "nonepileptic attack",
    "pseudoseizure",
    "pseudoseizures",
    # Dissociative subtypes
    "dissociative identity disorder",
    "dissociative convulsion",
    # Other
    "astasia-abasia",
    "idiopathic dystonia",
    "functional neurological",
]

OS_RECALL_IMAGING_TERMS = [
    # Original OS terms
    "neuro imaging",
    "neuroimaging",
    "magnetic resonance imaging",
    "fMRI",
    "MRI",
    "VBM",
    "PET",
    # Additional imaging modalities present in Table 1
    "SPECT",
    "single photon emission",
    "EEG",
    "electroencephalography",
    "MEG",
    "magnetoencephalography",
    "computed tomography",
    "positron emission tomography",
    "brain imaging",
]


# Ludwig et al. (2018) validation terms. The published search was a 3-block
# AND: (FND terms) AND (stressor terms) AND (study-design terms).
# Searched PubMed and Science Direct, 1965 to Nov 4 2016.
LUDWIG_FND_TERMS = [
    "psychogenic",
    "conversion disorder",
    "non-epileptic",
]

LUDWIG_STRESSOR_TERMS = [
    "abuse",
    "life event",
]

LUDWIG_DESIGN_TERMS = [
    "control",
    "controlled",
    "case-control",
]


@dataclass
class SearchTermConfig:
    """Container for search term blocks. block_c is optional (3-block queries)."""
    block_a: list[str]
    block_b: list[str]
    block_c: list[str] | None = None


def _active_terms() -> tuple[list[str], list[str]]:
    """Return FND and imaging/topic term lists for the current search mode.

    For backward compatibility, returns a 2-tuple. Ludwig mode assembles a
    3-block query internally via _active_term_config().
    """
    config = _active_term_config()
    return config.block_a, config.block_b


def _active_term_config() -> SearchTermConfig:
    """Return full search term configuration for the current search mode."""
    if SEARCH_MODE == "os_validation":
        return SearchTermConfig(OS_FND_TERMS, OS_IMAGING_TERMS)
    if SEARCH_MODE == "os_table_recall":
        return SearchTermConfig(OS_RECALL_FND_TERMS, OS_RECALL_IMAGING_TERMS)
    if SEARCH_MODE == "ludwig_validation":
        return SearchTermConfig(
            LUDWIG_FND_TERMS, LUDWIG_STRESSOR_TERMS, LUDWIG_DESIGN_TERMS,
        )
    return SearchTermConfig(FND_TERMS, IMAGING_TERMS)


def _date_filter_pubmed() -> str:
    """Build PubMed date filter."""
    start = f"{SEARCH_START_YEAR}/01/01" if SEARCH_START_YEAR else "1800/01/01"
    return (
        f'AND ("{start}"[Date - Publication] : '
        f'"{SEARCH_END_DATE}"[Date - Publication])'
    )


def _date_filter_year_range() -> str:
    """Build year range for APIs that accept only publication years."""
    start = SEARCH_START_YEAR if SEARCH_START_YEAR else 1800
    end = int(SEARCH_END_DATE[:4])
    return f"{start} TO {end}"


def _scopus_date_filter() -> str:
    """Build Scopus publication-year filter."""
    end = int(SEARCH_END_DATE[:4])
    if SEARCH_START_YEAR:
        return f" AND PUBYEAR > {SEARCH_START_YEAR - 1} AND PUBYEAR < {end + 1}"
    return f" AND PUBYEAR < {end + 1}"


def _build_wos_phrase_or_block(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def _build_europepmc_phrase_or_block(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def _build_scopus_phrase_or_block(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def _build_pubmed_text_block(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"[tiab]' for t in terms)


def build_pubmed_query() -> str:
    """PubMed syntax: uses [MeSH Terms], [tiab], field tags."""
    config = _active_term_config()
    fnd_terms, imaging_terms = config.block_a, config.block_b
    if SEARCH_MODE in _VALIDATION_MODES:
        fnd_block = _build_pubmed_text_block(fnd_terms)
        imaging_block = _build_pubmed_text_block(imaging_terms)
        if SEARCH_MODE == "os_validation":
            imaging_block += (
                ' OR ("magnetic"[tiab] AND "resonance"[tiab] AND "imaging"[tiab])'
            )
        query = f"({fnd_block}) AND ({imaging_block})"
        if config.block_c:
            design_block = _build_pubmed_text_block(config.block_c)
            query += f" AND ({design_block})"
        return f"{query} {_date_filter_pubmed()}"

    fnd_block = (
        '("Conversion Disorder"[MeSH] OR "Dissociative Disorders"[MeSH] '
        'OR ' + _build_pubmed_text_block(fnd_terms) + ')'
    )
    imaging_block = (
        '("Neuroimaging"[MeSH] OR "Magnetic Resonance Imaging"[MeSH] '
        'OR "Diffusion Tensor Imaging"[MeSH] OR "Positron-Emission Tomography"[MeSH] '
        'OR "Tomography, Emission-Computed, Single-Photon"[MeSH] '
        'OR ' + _build_pubmed_text_block(imaging_terms) + ')'
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
    config = _active_term_config()
    fnd = _build_wos_phrase_or_block(config.block_a)
    imag = _build_wos_phrase_or_block(config.block_b)
    if SEARCH_MODE == "os_validation":
        imag = f'{imag} OR ("magnetic" AND "resonance" AND "imaging")'
    year_range = _date_filter_year_range().replace(" TO ", "-")
    date_part = f" AND PY={year_range}"
    no_lang_modes = {"os_table_recall", "ludwig_validation"}
    lang_part = "" if SEARCH_MODE in no_lang_modes else " AND LA=(English)"
    query = f'TS=({fnd}) AND TS=({imag})'
    if config.block_c:
        design = _build_wos_phrase_or_block(config.block_c)
        query += f' AND TS=({design})'
    return f'{query}{lang_part}{date_part}'


def build_europepmc_query() -> str:
    """Europe PMC syntax: similar to Lucene. Uses TITLE_ABS, PUB_YEAR."""
    config = _active_term_config()
    fnd = _build_europepmc_phrase_or_block(config.block_a)
    imag = _build_europepmc_phrase_or_block(config.block_b)
    if SEARCH_MODE == "os_validation":
        imag = f'{imag} OR ("magnetic" AND "resonance" AND "imaging")'
    date_part = f" AND (PUB_YEAR:[{_date_filter_year_range()}])"
    no_lang_modes = {"os_table_recall", "ludwig_validation"}
    lang_part = '' if SEARCH_MODE in no_lang_modes else ' AND (LANG:"eng")'
    query = f'(TITLE_ABS:({fnd})) AND (TITLE_ABS:({imag}))'
    if config.block_c:
        design = _build_europepmc_phrase_or_block(config.block_c)
        query += f' AND (TITLE_ABS:({design}))'
    return f'{query}{lang_part}{date_part}'


def build_scopus_query() -> str:
    """Scopus syntax: TITLE-ABS-KEY field tag, AND/OR Boolean."""
    config = _active_term_config()
    fnd = _build_scopus_phrase_or_block(config.block_a)
    imag = _build_scopus_phrase_or_block(config.block_b)
    if SEARCH_MODE == "os_validation":
        imag = f'{imag} OR ("magnetic" AND "resonance" AND "imaging")'
    date_part = _scopus_date_filter()
    no_lang_modes = {"os_table_recall", "ludwig_validation"}
    lang_part = "" if SEARCH_MODE in no_lang_modes else " AND LANGUAGE(english)"
    query = f'(TITLE-ABS-KEY({fnd})) AND (TITLE-ABS-KEY({imag}))'
    if config.block_c:
        design = _build_scopus_phrase_or_block(config.block_c)
        query += f' AND (TITLE-ABS-KEY({design}))'
    return f'{query}{date_part}{lang_part}'


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
    volume: str = ""
    issue: str = ""
    pages: str = ""
    isbn: str = ""
    issn: str = ""
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def _title_year_key(self) -> str:
        """Title+year-based dedup key (ignores DOI)."""
        title_norm = "".join(c.lower() for c in self.title if c.isalnum())[:80]
        return f"tyh:{hashlib.md5(f'{title_norm}_{self.year}'.encode()).hexdigest()}"

    def dedup_key(self) -> str:
        """Preferred dedup key: DOI (normalized) > title+year hash."""
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        return self._title_year_key()


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
                volume=art.findtext(".//Volume") or "",
                issue=art.findtext(".//Issue") or "",
                # MedlinePagination (e.g. "123-9") or individual page fields
                pages=(art.findtext(".//MedlinePagination")
                       or art.findtext(".//StartPage") or ""),
                issn=art.findtext(".//ISSN") or "",
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

        # Volume/issue/ISSN are nested inside journalInfo
        ji = h.get("journalInfo", {}) or {}
        journal = ji.get("journal", {}) or {}

        return Record(
            source_db="europepmc",
            source_id=h.get("id", ""),
            doi=h.get("doi"),
            title=h.get("title", ""),
            abstract=h.get("abstractText", ""),
            authors=[a.strip() for a in (h.get("authorString") or "").split(",") if a.strip()],
            journal=journal.get("title", "") or h.get("journalTitle", "") or "",
            year=year,
            pub_date=h.get("firstPublicationDate", ""),
            keywords=h.get("keywordList", {}).get("keyword", []) if h.get("keywordList") else [],
            mesh_terms=[m.get("descriptorName", "") for m in
                        (h.get("meshHeadingList", {}) or {}).get("meshHeading", [])],
            pub_types=[p for p in (h.get("pubTypeList", {}) or {}).get("pubType", [])],
            volume=str(ji.get("volume", "") or ""),
            issue=str(ji.get("issue", "") or ""),
            pages=h.get("pageInfo", "") or "",
            issn=journal.get("issn", "") or journal.get("essn", "") or "",
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
    """Elsevier Scopus Search + Abstract Retrieval APIs.

    Search tries COMPLETE view (full author list + metadata) first, falling
    back to STANDARD view if the API key lacks COMPLETE entitlement.
    Abstracts are fetched in a second pass via Abstract Retrieval API with
    META_ABS view, which includes dc:description without requiring FULL-view
    entitlement.
    """

    BASE = "https://api.elsevier.com/content/search/scopus"
    ABSTRACT_BASE = "https://api.elsevier.com/content/abstract"
    ABSTRACT_VIEWS = ("META_ABS", "META", "FULL")
    ABSTRACT_DELAY = 0.35  # seconds between abstract retrieval calls
    SEARCH_VIEWS = ("COMPLETE", "STANDARD")  # preference order for search

    @retry()
    def search(self, query: str, count: int = 100) -> list[Record]:
        if not SCOPUS_API_KEY:
            log.warning("SCOPUS_API_KEY not set — skipping Scopus")
            return []
        log.info(f"Scopus query: {query[:200]}...")
        headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}

        # Probe which search view the API key is entitled to.
        view = self._probe_search_view(headers)
        log.info(f"Scopus Search: using view={view}")

        records: list[Record] = []
        start = 0
        page_size = min(count, 25)
        if page_size != count:
            log.info(f"Scopus page size reduced to {page_size} to match the service-level maximum")
        while True:
            params = {"query": query, "count": page_size, "start": start, "view": view}
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
            start += page_size
            if start >= total:
                break
            time.sleep(0.3)

        return records

    def _probe_search_view(self, headers: dict) -> str:
        """Return the best search view the API key is entitled to.

        COMPLETE view includes the full author list (``author`` array with
        ``authname``) and all bibliographic fields. STANDARD view includes
        only ``dc:creator`` (first author) but still has volume/issue/pages.

        Some institutional API keys lack COMPLETE entitlement, so we probe
        with a minimal request and fall back gracefully.
        """
        for v in self.SEARCH_VIEWS:
            try:
                params = {"query": "all(test)", "count": 1, "view": v}
                r = requests.get(self.BASE, headers=headers,
                                 params=params, timeout=30)
                if r.status_code == 200:
                    entries = (r.json()
                               .get("search-results", {})
                               .get("entry", []))
                    if not entries or entries[0].get("error"):
                        # View returned no usable data, try next
                        continue
                    return v
                # 400/403 typically means entitlement error
                log.debug(f"  Scopus view={v} returned {r.status_code}")
            except (requests.RequestException, ValueError):
                continue
        # Fall back to STANDARD — always available
        log.warning("Scopus: could not probe views; defaulting to STANDARD")
        return "STANDARD"

    def _enrich_abstracts(self, records: list[Record]) -> None:
        """Fetch abstracts via Abstract Retrieval API for records missing them."""
        need = [r for r in records if not r.abstract and (r.doi or r.source_id)]
        if not need:
            return
        log.info(f"Scopus: fetching abstracts for {len(need)} records via Abstract Retrieval API")

        view = self._probe_abstract_view()
        if view is None:
            log.warning("Scopus Abstract Retrieval: no accessible view found; skipping enrichment")
            return
        log.info(f"Scopus Abstract Retrieval: using view={view}")

        fetched = 0
        failed = 0
        authors_filled = 0
        for i, rec in enumerate(need, 1):
            abstract, authors = self._fetch_abstract_and_authors(
                rec.doi, rec.source_id, view)
            if abstract:
                rec.abstract = abstract
                fetched += 1
            else:
                failed += 1
            # The Search API (STANDARD view) only gives dc:creator (first
            # author); replace it with the full list from Abstract Retrieval
            # whenever one is returned.
            if authors:
                rec.authors = authors
                authors_filled += 1
            if i % 50 == 0:
                log.info(f"  Abstract retrieval progress: {i}/{len(need)} "
                         f"(abstracts={fetched}, authors={authors_filled}, "
                         f"failed={failed})")
            time.sleep(self.ABSTRACT_DELAY)

        log.info(f"Scopus Abstract Retrieval done: {fetched} abstracts, "
                 f"{authors_filled} full author lists, "
                 f"{failed} unavailable out of {len(need)} attempted")

    def _probe_abstract_view(self) -> str | None:
        """Try views in preference order on a known DOI to find one that works."""
        headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}
        test_doi = "10.1038/npp.2015.79"
        for view in self.ABSTRACT_VIEWS:
            try:
                url = f"{self.ABSTRACT_BASE}/doi/{test_doi}"
                r = requests.get(url, headers=headers, params={"view": view}, timeout=30)
                if r.status_code == 200:
                    return view
                log.debug(f"  Abstract Retrieval view={view} returned {r.status_code}")
            except requests.RequestException:
                continue
            time.sleep(0.3)
        return None

    def _fetch_abstract_and_authors(self, doi: str | None, scopus_id: str | None,
                                    view: str) -> tuple[str, list[str]]:
        """Retrieve abstract text and the full author list for one document.

        The Scopus Search API (STANDARD view) returns only ``dc:creator``
        (first author). The full author list lives in the Abstract Retrieval
        response under ``abstracts-retrieval-response.authors.author``, so we
        harvest both abstract and authors from the same call used for
        abstract enrichment (no extra requests).
        """
        headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}
        if doi:
            url = f"{self.ABSTRACT_BASE}/doi/{doi}"
        elif scopus_id:
            url = f"{self.ABSTRACT_BASE}/scopus_id/{scopus_id}"
        else:
            return "", []
        try:
            r = requests.get(url, headers=headers, params={"view": view}, timeout=30)
            if r.status_code != 200:
                return "", []
            resp = r.json().get("abstracts-retrieval-response", {})
            coredata = resp.get("coredata", {})
            abstract = coredata.get("dc:description", "")
            if isinstance(abstract, dict):
                abstract = abstract.get("$", "")
            authors = self._parse_abstract_authors(resp.get("authors"))
            return abstract.strip(), authors
        except (requests.RequestException, ValueError, KeyError):
            return "", []

    @staticmethod
    def _parse_abstract_authors(authors_node: Any) -> list[str]:
        """Extract author display names from an Abstract Retrieval ``authors`` node.

        The node shape is view/version dependent but typically::

            {"author": [{"@auid": "...", "preferred-name": {
                "ce:indexed-name": "Smith J.",
                "ce:surname": "Smith", "ce:given-name": "John",
                "ce:initials": "J."}}, ...]}

        Older responses may put ``ce:surname``/``authname`` directly on the
        author object. We prefer ``ce:indexed-name`` (Scopus's canonical
        "Surname I." form, matching ``dc:creator``) and fall back to building
        the name from surname + given name.
        """
        if not authors_node:
            return []
        alist = authors_node.get("author", []) if isinstance(authors_node, dict) else []
        # Single-author responses occasionally use a dict instead of a list.
        if isinstance(alist, dict):
            alist = [alist]
        names: list[str] = []
        for a in alist:
            if not isinstance(a, dict):
                continue
            pref = a.get("preferred-name") or {}
            name = (a.get("ce:indexed-name")
                    or pref.get("ce:indexed-name")
                    or a.get("authname"))
            if not name:
                surname = pref.get("ce:surname") or a.get("ce:surname")
                given = (pref.get("ce:given-name")
                         or pref.get("ce:initials")
                         or a.get("ce:given-name"))
                if surname:
                    name = f"{surname} {given}".strip() if given else surname
            if name:
                names.append(str(name).strip())
        return names

    @staticmethod
    def _parse(e: dict[str, Any]) -> Record:
        year = None
        cover_date = e.get("prism:coverDate", "")
        if cover_date:
            try:
                year = int(cover_date[:4])
            except ValueError:
                pass

        # Authors: COMPLETE view returns an ``author`` array with authname;
        # STANDARD view returns only ``dc:creator`` (first author string).
        author_list = e.get("author", [])
        if author_list:
            authors = [a.get("authname", "") for a in author_list if a.get("authname")]
        else:
            dc_creator = e.get("dc:creator", "")
            authors = [dc_creator] if dc_creator else []

        # ISBN/ISSN: Scopus may return these as strings, lists of strings,
        # or lists of dicts (e.g. {"$": "value"}).
        def _safe_str(v: Any) -> str:
            if isinstance(v, dict):
                # Prefer the "$" text node used by the Scopus XML→JSON mapping
                return str(v.get("$", list(v.values())[0] if v else ""))
            return str(v)

        isbn = e.get("prism:isbn", "")
        if isinstance(isbn, list):
            isbn = "; ".join(_safe_str(x) for x in isbn if x)
        issn = e.get("prism:issn", "")
        if isinstance(issn, list):
            issn = "; ".join(_safe_str(x) for x in issn if x)

        return Record(
            source_db="scopus",
            source_id=e.get("dc:identifier", "").replace("SCOPUS_ID:", ""),
            doi=e.get("prism:doi"),
            title=e.get("dc:title", ""),
            abstract=e.get("dc:description", ""),
            authors=authors,
            journal=e.get("prism:publicationName", ""),
            year=year,
            pub_date=cover_date,
            keywords=[kw.strip() for kw in (e.get("authkeywords") or "").split("|") if kw.strip()],
            volume=e.get("prism:volume", ""),
            issue=e.get("prism:issueIdentifier", ""),
            pages=e.get("prism:pageRange", ""),
            isbn=isbn,
            issn=issn,
            url=next((l.get("@href", "") for l in e.get("link", [])
                      if l.get("@ref") == "scopus"), ""),
        )


# ---------------------------------------------------------------------------
# DEDUPLICATION + EXPORT
# ---------------------------------------------------------------------------

def _titles_similar(title_a: str, title_b: str, threshold: float = 0.4) -> bool:
    """Return True if two titles are similar enough to be the same work.

    Uses Jaccard similarity on word sets (words >= 3 chars, lowered).
    A low threshold (0.4) avoids false merges while still catching
    minor punctuation / transliteration differences.
    """
    def _words(t: str) -> set[str]:
        return {w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", t)}

    w1, w2 = _words(title_a), _words(title_b)
    if not w1 or not w2:
        return True
    return len(w1 & w2) / len(w1 | w2) >= threshold


def deduplicate_simple(records: list[Record]) -> tuple[list[Record], dict[str, int]]:
    """Dedup by DOI when available, else by normalized title+year hash.

    When two records share a DOI but have substantially different titles,
    both are kept and a warning is logged (likely a DOI metadata error in
    one database).  First-pass dedup only; Rayyan/ASReview will refine.
    """
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

    if doi_collisions:
        log.warning(
            f"DOI collision(s) detected — {len(doi_collisions)} record pair(s) "
            "had matching DOIs but different titles; both kept:"
        )
        for existing, new in doi_collisions:
            log.warning(
                f"  DOI {existing.doi}:\n"
                f"    kept   : '{existing.title}' ({existing.source_db})\n"
                f"    rescued: '{new.title}' ({new.source_db})"
            )

    stats = {
        "total_raw": len(records),
        "unique": len(seen),
        "duplicates_removed": len(records) - len(seen),
        "doi_collisions_rescued": len(doi_collisions),
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
            if r.volume:
                f.write(f"VL  - {r.volume}\n")
            if r.issue:
                f.write(f"IS  - {r.issue}\n")
            if r.pages:
                f.write(f"SP  - {r.pages}\n")
            if r.isbn:
                f.write(f"SN  - {r.isbn}\n")
            elif r.issn:
                f.write(f"SN  - {r.issn}\n")
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
    if SEARCH_MODE == "os_validation":
        search_scope_note = (
            "OS validation mode approximates the Boeckle et al. (2016) search "
            "terms and end date for pipeline validation only. It is not the "
            "expanded production search strategy."
        )
        filters_applied = {
            "language": "English in non-PubMed API queries where supported",
            "date": f"inception to {SEARCH_END_DATE}",
            "screening_filters": (
                "Human/adult/primary research criteria are applied during "
                "screening to stay close to the original study workflow."
            ),
        }
    elif SEARCH_MODE == "os_table_recall":
        search_scope_note = (
            "Table-recall mode uses broadened search terms to maximise "
            "recovery of the 49 studies in Boeckle et al. Table 1. Language "
            "filters are NOT applied at the search stage; apply English-"
            "language screening downstream to match the original workflow."
        )
        filters_applied = {
            "language": "None at search stage — apply during screening",
            "date": f"inception to {SEARCH_END_DATE}",
            "screening_filters": (
                "Language (English), human/adult, and primary-research "
                "criteria should all be applied during screening."
            ),
        }
    elif SEARCH_MODE == "ludwig_validation":
        search_scope_note = (
            "Ludwig validation mode replicates the search strategy from "
            "Ludwig et al. (2018) Lancet Psychiatry (trauma/stressors in "
            "FND). Uses a 3-block AND query: FND terms x stressor terms x "
            "study-design terms. Date range: inception to 2016/11/04. "
            "Language filters are NOT applied at search stage."
        )
        filters_applied = {
            "language": "None at search stage — apply during screening",
            "date": f"inception to {SEARCH_END_DATE}",
            "query_structure": "3-block AND (FND x stressor x study-design)",
            "screening_filters": (
                "Language (English) applied during screening."
            ),
        }
    else:
        search_scope_note = (
            "Case reports, reviews, and non-primary research are NOT excluded "
            "at search stage per PRISMA 2020 recommendations. They are "
            "excluded during title/abstract screening."
        )
        filters_applied = {
            "language": "English",
            "subject": "Humans (PubMed only — other DBs filtered at screening)",
            "excluded_pub_types": ["Editorial", "Letter", "Comment"],
        }

    _search_profiles = {
        "os_validation": "Boeckle et al. 2016 validation approximation",
        "os_table_recall": "Boeckle et al. 2016 Table 1 recall (broadened terms)",
        "ludwig_validation": "Ludwig et al. 2018 trauma-in-FND validation",
    }
    prisma_meta = {
        "run_id": RUN_ID,
        "search_mode": SEARCH_MODE,
        "search_profile": _search_profiles.get(
            SEARCH_MODE, "expanded FND neuroimaging protocol"
        ),
        "search_date": datetime.now(timezone.utc).isoformat(),
        "search_range": (
            f"{SEARCH_START_YEAR}-01-01 to {SEARCH_END_DATE}"
            if SEARCH_START_YEAR else f"inception to {SEARCH_END_DATE}"
        ),
        "databases_searched": list(queries.keys()),
        "databases_not_automated": ["PsycINFO (searched manually via OVID/EBSCOhost)"],
        "queries": queries,
        "records_per_database": per_db_counts,
        "deduplication": dedup_stats,
        "filters_applied": filters_applied,
        "notes": search_scope_note,
    }
    meta_path = OUTPUT_DIR / "prisma_search_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(prisma_meta, f, indent=2)
    log.info(f"Wrote PRISMA metadata -> {meta_path}")


# ---------------------------------------------------------------------------
# INTERACTIVE HELPERS
# ---------------------------------------------------------------------------

def _confirm(prompt: str) -> bool:
    """Ask user for yes/no confirmation. Returns True on 'y'/'yes'."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    log.info(f"Search mode: {SEARCH_MODE}")
    if SEARCH_MODE == "os_validation":
        log.info("Using Boeckle et al. (2016) validation terms")
    elif SEARCH_MODE == "os_table_recall":
        log.info("Using broadened terms for Table 1 recall (no language filter at search stage)")
    elif SEARCH_MODE == "ludwig_validation":
        log.info("Using Ludwig et al. (2018) trauma-in-FND validation terms (3-block query)")
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

    # -- Summary of search results ------------------------------------------
    log.info("=" * 60)
    log.info("Search results summary:")
    total_raw = sum(per_db.values())
    for db, n in per_db.items():
        log.info(f"  {db}: {n} records")
    log.info(f"  TOTAL: {total_raw} raw records")
    log.info("=" * 60)

    # -- Scopus abstract enrichment (gated) ---------------------------------
    scopus_count = per_db.get("scopus", 0)
    scopus_abstracts_fetched = False
    if scopus_count > 0 and not AUTO_MODE:
        log.info(
            f"Scopus returned {scopus_count} records. Abstract enrichment "
            f"requires one API call per record and may take a while."
        )
        if _confirm("Fetch Scopus abstracts?"):
            scopus_abstracts_fetched = True
        else:
            log.info("Skipping Scopus abstract enrichment (re-run with --auto to skip this prompt)")

    # -- Scopus pre-dedup enrichment (ASySD) -------------------------------
    # ASySD dedup uses author + abstract similarity, but the Scopus Search API
    # (STANDARD view) returns only the first author (dc:creator) and no
    # abstract. Enrich ALL Scopus records (abstracts + full author lists) BEFORE
    # deduplication so the matcher sees real data. This is one call per Scopus
    # record (~192); simple dedup skips this and enriches post-dedup instead.
    if DEDUP_METHOD == "asysd" and (scopus_abstracts_fetched or AUTO_MODE):
        scopus_all = [r for r in all_records if r.source_db == "scopus"]
        if scopus_all:
            log.info(f"Enriching {len(scopus_all)} Scopus records (abstracts + "
                     f"authors) before ASySD dedup")
            ScopusClient()._enrich_abstracts(scopus_all)

    # -- Deduplication ------------------------------------------------------
    log.info(f"Total raw records across all DBs: {len(all_records)}")
    log.info(f"Deduplication method: {DEDUP_METHOD}")

    maybe_pairs_data = []

    if DEDUP_METHOD == "asysd" and deduplicate_asysd is not None:
        # Convert Records to dicts for ASySD
        asysd_input = []
        for r in all_records:
            asysd_input.append({
                "source": r.source_db,
                "record_id": r.source_id,
                "author": "; ".join(r.authors) if r.authors else None,
                "title": r.title,
                "year": str(r.year) if r.year else None,
                "journal": r.journal,
                "abstract": r.abstract,
                "doi": r.doi,
                "pages": r.pages or None,
                "volume": r.volume or None,
                "number": r.issue or None,
                "isbn": r.isbn or None,
                "label": r.source_db,
            })
        asysd_unique, asysd_stats, maybe_pairs_data = deduplicate_asysd(
            asysd_input, keep_source="pubmed"
        )

        # Convert back: map unique record_ids back to Record objects
        # Build index of all records by source_id
        record_by_id: dict[str, Record] = {}
        for r in all_records:
            record_by_id[r.source_id] = r

        deduped = []
        for rec_dict in asysd_unique:
            rid = rec_dict.get("record_id", "")
            if rid in record_by_id:
                deduped.append(record_by_id[rid])
            else:
                # Fallback: search by duplicate_id
                dup_id = rec_dict.get("duplicate_id", "")
                if dup_id in record_by_id:
                    deduped.append(record_by_id[dup_id])

        dedup_stats = {
            "total_raw": asysd_stats["total_raw"],
            "unique": len(deduped),
            "duplicates_removed": asysd_stats["duplicates_removed"],
            "method": "asysd",
        }

        # Export maybe_pairs to CSV
        if maybe_pairs_data:
            maybe_path = OUTPUT_DIR / "maybe_pairs.csv"
            with open(maybe_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(maybe_pairs_data[0].keys()))
                w.writeheader()
                for row in maybe_pairs_data:
                    w.writerow(row)
            log.info(f"Wrote {len(maybe_pairs_data)} maybe-pairs -> {maybe_path}")

    else:
        if DEDUP_METHOD == "asysd" and deduplicate_asysd is None:
            log.warning("ASySD dedup not available (dedup_asysd module not found), "
                        "falling back to simple dedup")
        deduped, dedup_stats = deduplicate_simple(all_records)
        dedup_stats["method"] = "simple"

    log.info(f"After dedup: {len(deduped)} unique records "
             f"({dedup_stats['duplicates_removed']} duplicates removed)")

    # Fetch abstracts only for deduplicated Scopus-sourced records missing them.
    # PubMed/Europe PMC already include abstracts; duplicates have been removed.
    if AUTO_MODE or scopus_abstracts_fetched:
        scopus_need_abstract = [r for r in deduped
                                if r.source_db == "scopus" and not r.abstract]
        if scopus_need_abstract:
            log.info(f"Fetching abstracts for {len(scopus_need_abstract)} Scopus-only "
                     f"records (post-dedup)")
            ScopusClient()._enrich_abstracts(scopus_need_abstract)

    export_results(deduped, all_records_by_db, queries, per_db, dedup_stats)

    log.info("=" * 60)
    log.info("PRISMA flow diagram numbers:")
    for db, n in per_db.items():
        log.info(f"  Records identified from {db}: {n}")
    log.info(f"  Records after duplicates removed: {dedup_stats['unique']}")
    if dedup_stats.get("method") == "simple" and "doi_collisions_rescued" in dedup_stats:
        log.info(f"  DOI collisions rescued: {dedup_stats['doi_collisions_rescued']}")
    log.info("=" * 60)
    log.info("Next step: import records_deduplicated.ris into Rayyan or ASReview")
    log.info("for title/abstract screening.")


if __name__ == "__main__":
    main()
