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

Workflow modes:
  - Default:    search + dedup in one pass
  - --no-dedup: search only; save raw CSVs + queries for manual databases;
                run --dedup <dir> later after adding manual exports
  - --dedup DIR: load all sources in an existing search directory, deduplicate,
                 and export final PRISMA artifacts

Dependencies:
    pip install biopython requests python-dotenv

Repository: https://github.com/dvozenil/fmd-meta-analysis
"""

from __future__ import annotations

import argparse
import copy
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
        "--dedup-algo", choices=["asysd", "simple"], default="asysd",
        help="Deduplication algorithm: 'asysd' (ASySD-class, default) or "
             "'simple' (old DOI+title hash dedup)",
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Run search only; skip deduplication (for two-phase workflow). "
             "Use --dedup <dir> later to deduplicate after adding manual exports.",
    )
    parser.add_argument(
        "--dedup", metavar="DIR", dest="dedup_dir",
        help="Dedup-only mode: load all sources in an existing search directory, "
             "deduplicate, and export final PRISMA artifacts.",
    )
    parser.add_argument(
        "--skip-abstract-recovery", action="store_true",
        help="Skip cross-database abstract recovery (useful when re-deduping "
             "a folder whose raw CSVs already have recovered abstracts).",
    )
    return parser.parse_args()

_cli_args = _parse_args()
AUTO_MODE: bool = _cli_args.auto
DEDUP_METHOD: str = _cli_args.dedup_algo
NO_DEDUP: bool = _cli_args.no_dedup
DEDUP_ONLY_DIR: str | None = _cli_args.dedup_dir
SKIP_ABSTRACT_RECOVERY: bool = _cli_args.skip_abstract_recovery

# ---------------------------------------------------------------------------
# CONFIGURATION (conditional on --search vs --dedup mode)
# ---------------------------------------------------------------------------

if DEDUP_ONLY_DIR:
    # --dedup mode: use the provided directory, skip search config
    OUTPUT_DIR = Path(DEDUP_ONLY_DIR)
    if not OUTPUT_DIR.is_dir():
        raise SystemExit(f"Search directory not found: {OUTPUT_DIR}")
    SEARCH_MODE = ""  # not used; loaded from queries.json later
    SEARCH_START_YEAR: int | None = None
    SEARCH_END_DATE = ""
    RUN_ID = OUTPUT_DIR.name
else:
    # --search mode (default or --no-dedup)
    SEARCH_MODE = _cli_args.mode or os.getenv("FND_SEARCH_MODE", "update")
    VALID_SEARCH_MODES = {"update", "full", "os_validation", "os_table_recall",
                          "ludwig_validation"}
    _VALIDATION_MODES = {"os_validation", "os_table_recall", "ludwig_validation"}
    if SEARCH_MODE not in VALID_SEARCH_MODES:
        raise ValueError(
            f"Unknown FND_SEARCH_MODE={SEARCH_MODE!r}; expected one of "
            f"{sorted(VALID_SEARCH_MODES)}"
        )
    SEARCH_START_YEAR = 2015 if SEARCH_MODE == "update" else None
    _VALIDATION_END_DATES = {
        "os_validation": "2015/08/31",
        "os_table_recall": "2015/08/31",
        "ludwig_validation": "2016/11/04",
    }
    DEFAULT_SEARCH_END_DATE = (
        _VALIDATION_END_DATES.get(SEARCH_MODE, datetime.now().strftime("%Y/%m/%d"))
    )
    SEARCH_END_DATE = os.getenv("FND_SEARCH_END_DATE", DEFAULT_SEARCH_END_DATE)
    RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR = Path(f"./fnd_search_{RUN_ID}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# NCBI credentials (required by NCBI; get a free API key at
# https://www.ncbi.nlm.nih.gov/account/settings/ for 10 req/s vs 3/s)
Entrez.email   = os.getenv("NCBI_EMAIL", "CHANGE_ME@institution.edu")
Entrez.api_key = os.getenv("NCBI_API_KEY")

# Institutional API keys — set as env vars, never hardcode
WOS_API_KEY    = os.getenv("WOS_API_KEY")     # Web of Science Expanded API
SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")  # Elsevier Developer Portal

# Module-level log instance — handlers configured in main() after OUTPUT_DIR is final
log = logging.getLogger(__name__)


def _setup_logging(search_dir: Path) -> None:
    """Configure logging to write to search_dir/search_log.txt.

    In --dedup mode, appends to the existing log file. In --search mode,
    overwrites (the file is new since the directory is new).
    """
    log_path = search_dir / "search_log.txt"
    mode = "a" if DEDUP_ONLY_DIR else "w"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode=mode),
            logging.StreamHandler(),
        ],
    )
    # Push config to root so module-level log picks it up
    log.handlers.clear()
    log.addHandler(logging.FileHandler(log_path, mode=mode))
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


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


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities (EuropePMC returns HTML in abstracts)."""
    if not text:
        return text
    text = (text.replace("&lt;", "<").replace("&gt;", ">")
                .replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'"))
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.split())


def _element_text(el: ET.Element | None) -> str:
    """Full text of an XML element, including nested tag contents.

    ``Element.findtext`` / ``.text`` only return the first text node, so
    PubMed titles like ``Effects of <i>TPH2</i> gene…`` become ``Effects of ``.
    """
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _normalize_doi(doi: str | None) -> str | None:
    """Normalize a DOI for matching; return None if missing/invalid."""
    if doi is None:
        return None
    d = str(doi).strip()
    if not d or d.upper() == "NA":
        return None
    d_up = d.upper()
    for prefix in ("HTTPS://DX.DOI.ORG/", "HTTP://DX.DOI.ORG/",
                   "HTTPS://DOI.ORG/", "HTTP://DOI.ORG/"):
        if d_up.startswith(prefix):
            d = d[len(prefix):]
            d_up = d.upper()
            break
    if d_up.startswith("DOI:"):
        d = d[4:].strip()
    d = d.strip().lstrip("/").lower()
    if not d.startswith("10."):
        return None
    return d


def _namespaced_id(source_db: str, source_id: str) -> str:
    """Stable cross-database record id for ASySD graph nodes."""
    return f"{source_db}:{source_id}"


def _title_token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on alphanumeric tokens of length >= 3."""
    def words(t: str) -> set[str]:
        return {w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", t or "")}
    w1, w2 = words(a), words(b)
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)


# Erratum / correction marker detection — matches anywhere in the title
# (word-boundary), not just as a prefix.  This catches both:
#   "Erratum: Uncovering the etiology..."     (prefix — WoS/Scopus)
#   "...neuroimaging" Corrigendum             (suffix — PsycINFO)
_ERRATUM_TITLE_RE = re.compile(
    r"\b(?:erratum|errata|correction|corrigendum|corrigenda|"
    r"retract|retracted|retraction|retractions|withdrawal)\b",
    re.IGNORECASE,
)


def _is_erratum_title(title: str | None) -> bool:
    """True if a title marks a correction/erratum/retraction record."""
    if not title or not str(title).strip():
        return False
    return bool(_ERRATUM_TITLE_RE.search(str(title)))


# ---------------------------------------------------------------------------
# LAYER 1: QUERY CONSTRUCTION
# ---------------------------------------------------------------------------
# Three concept blocks, combined with AND:
#   BLOCK A — FND / conversion disorder terminology (old + new)
#   BLOCK B — Neuroimaging modalities (functional + structural)
#   BLOCK C — Optional filters (human, adult, English, date range)
# ---------------------------------------------------------------------------

# --- Concept A: FND terminology ---------------------------------------------
# Comprehensive list combining PROSPERO protocol terms with refinements.
# Truncation (*) is embedded in term strings to catch plural/variant forms
# (e.g. "dystoni*" matches dystonia, dystonias, dystonic). The * wildcard
# works inside quoted phrases in PubMed [tiab], Scopus TITLE-ABS-KEY,
# WoS TS=, and Europe PMC TITLE_ABS.
FND_TERMS = [
    # DSM-5 / ICD-11 preferred
    "functional neurological disorder*",
    "functional neurologic disorder*",
    "functional neurological symptom disorder*",
    "FNSD",
    # DSM-IV / ICD-10
    "conversion disorder*",
    "dissociative motor disorder*",
    "dissociative convulsion*",
    # General / legacy
    "conversion reaction*",
    "motor hysteria*",
    "medically unexplained symptom*",
    "non-organic",
    # Functional movement disorder spectrum — motor
    "functional motor disorder*",
    "psychogenic movement disorder*",
    "psychogenic motor disorder*",
    "functional movement disorder*",
    "functional tremor*",
    "psychogenic tremor*",
    "functional dystoni*",
    "psychogenic dystoni*",
    "functional myoclon*",
    "psychogenic myoclon*",
    "functional jerk*",
    "psychogenic jerk*",
    "functional gait*",
    "psychogenic gait*",
    "functional weakness*",
    "psychogenic weakness*",
    "functional paralys*",
    "psychogenic paralys*",
    "functional pares*",
    "psychogenic pares*",
    "functional parkinsonism*",
    "psychogenic parkinsonism*",
    "functional tic*",
    "psychogenic tic*",
    "functional tic-like behavio*",
    "psychogenic tic-like behavio*",
    "functional chorea*",
    "psychogenic chorea*",
    "functional dyskinesi*",
    "psychogenic dyskinesi*",
    "functional stereotyp*",
    "psychogenic stereotyp*",
    # Seizure variants
    "functional seizure*",
    "psychogenic seizure*",
    "psychogenic non-epileptic seizure*",
    "psychogenic nonepileptic seizure*",
    "PNES",
    "dissociative seizure*",
    "functional dissociative seizure*",
    "functional/dissociative seizure*",
    "FDS",
    "pseudoseizure*",
    "non-epileptic attack disorder*",
    "NEAD",
    # Sensory / vestibular / cognitive
    "functional sensory",
    "functional visual",
    "functional cognitive disorder*",
    "functional cognitive symptom*",
    "persistent postural-perceptual dizziness",
    "persistent postural perceptual dizziness",
    "PPPD",
    "functional dizziness",
    "psychogenic dizziness",
    "chronic subjective dizziness",
    "phobic postural vertigo",
    "functional vestibular disorder*",
    # Historical / legacy terms (needed for recall in older literature)
    "hysterical paralysis",
    "hysterical conversion",
    "motor conversion",
    "sensory conversion",
    "astasia-abasia",
]

# --- Concept B: Neuroimaging --------------------------------------------------
# Comprehensive list combining PROSPERO protocol terms.
# Truncation (*) is embedded in term strings to catch plural/variant forms
# (e.g. "morphometr*" matches morphometry, morphometric, morphometries).
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
    "BOLD",
    "blood oxygen level dependent",
    "task-based",
    "task-related",
    "activation likelihood",
    "neural activation",
    "brain activation",
    # MRI — structural
    "structural MRI",
    "sMRI",
    "structural magnetic resonance",
    "voxel-based morphometr*",
    "VBM",
    "surface-based morphometr*",
    "SBM",
    "cortical thickness",
    "cortical surface",
    "cortical volume",
    "grey matter",
    "gray matter",
    "GMV",
    "GMD",
    "white matter volume",
    "brain volume",
    "regional volume",
    "morphometr*",
    "neuroanatom*",
    # MRI — resting-state
    "resting state",
    "resting-state",
    "rs-fMRI",
    "rsfMRI",
    "functional connectivit*",
    "intrinsic connectivit*",
    "default mode network",
    "DMN",
    "ALFF",
    "amplitude of low frequency fluctuat*",
    "fALFF",
    "ReHo",
    "regional homogeneit*",
    "seed-based",
    "independent component analys*",
    # Diffusion
    "DWI",
    "diffusion-weighted imag*",
    "diffusion weighted imag*",
    "DTI",
    "diffusion tensor imag*",
    "diffusion MRI",
    "dMRI",
    "tractograph*",
    "fractional anisotrop*",
    "mean diffusivit*",
    "axial diffusivit*",
    "radial diffusivit*",
    "white matter integrity",
    "white matter microstructur*",
    "structural connectivity",
    "tract-based spatial statistic*",
    "TBSS",
    "NODDI",
    # Nuclear medicine
    "positron emission tomograph*",
    "PET",
    "single photon emission*",
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


def _build_ebsco_tiabsu_block(terms: list[str]) -> str:
    """Build EBSCO (TI OR AB OR SU) block for a list of terms.

    SU (Subjects) in APA PsycInfo indexes both author-supplied keywords
    and APA Thesaurus controlled subject headings — verified broader
    coverage than KW (author keywords only) and narrower than TX
    (All Text, which hits full text and returns ~88% noise).
    """
    phrase_or = " OR ".join(f'"{t}"' for t in terms)
    return f'(TI ({phrase_or}) OR AB ({phrase_or}) OR SU ({phrase_or}))'


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


def build_ebsco_psycinfo_query() -> str:
    """EBSCOhost APA PsycInfo / PsycArticles syntax.

    Uses TI (Title), AB (Abstract), and SU (Subjects — includes author
    keywords + APA Thesaurus controlled subject headings).  Date filter
    via PY year range.

    This query is NOT executed automatically (no EBSCO REST API exists).
    It is written to queries.json / queries.txt for manual search and
    export from the EBSCOhost web UI.
    """
    config = _active_term_config()
    fnd = _build_ebsco_tiabsu_block(config.block_a)
    imag = _build_ebsco_tiabsu_block(config.block_b)
    if SEARCH_MODE == "os_validation":
        imag = (
            f'{imag} OR '
            f'(TI (magnetic AND resonance AND imaging) '
            f'OR AB (magnetic AND resonance AND imaging) '
            f'OR SU (magnetic AND resonance AND imaging))'
        )
    year_range = _date_filter_year_range().replace(" TO ", "-")
    date_part = f" AND PY {year_range}"
    no_lang_modes = {"os_table_recall", "ludwig_validation"}
    lang_part = "" if SEARCH_MODE in no_lang_modes else " AND LA English"
    query = f"({fnd}) AND ({imag})"
    if config.block_c:
        design = _build_ebsco_tiabsu_block(config.block_c)
        query += f" AND ({design})"
    return f"{query}{lang_part}{date_part}"


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
        if total > len(pmids):
            log.error(
                f"PubMed returned {total} hits but only {len(pmids)} IDs were "
                f"retrieved (retmax={retmax}). Raise retmax or paginate; "
                f"refusing to continue with a truncated result set."
            )
            raise RuntimeError(
                f"PubMed result truncated: {len(pmids)}/{total} IDs retrieved"
            )

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
            title = _element_text(art.find(".//ArticleTitle"))
            abstract = " ".join(
                _element_text(e) for e in art.findall(".//Abstract/AbstractText")
            ).strip()
            journal = art.findtext(".//Journal/Title") or ""
            year_text = art.findtext(".//PubDate/Year") or ""
            try:
                year = int(year_text) if year_text else None
            except ValueError:
                year = None
            # Use ELocationID as primary DOI source — ArticleIdList
            # contains reference DOIs that can shadow the article's own.
            doi = None
            for eloc in art.findall(".//ELocationID"):
                if eloc.attrib.get("EIdType") == "doi":
                    doi = _normalize_doi(eloc.text)
                    break
            if not doi:
                # Fall back to first ArticleId doi (not last — the list
                # includes reference DOIs).
                for aid in art.findall(".//ArticleId"):
                    if aid.attrib.get("IdType") == "doi":
                        doi = _normalize_doi(aid.text)
                        break
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
            doi=_normalize_doi(h.get("doi")),
            title=_strip_html(h.get("title", "")),
            abstract=_strip_html(h.get("abstractText", "")),
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
                doi = _normalize_doi(ident.get("value"))
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
            # Use POST to avoid 413 Payload Too Large with expanded terms
            r = requests.post(self.BASE, headers=headers, data=params, timeout=60)
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
        """Fetch full author lists (and attempt abstracts) via Abstract Retrieval API.

        With the COMPLETE search view, most Scopus records already include
        ``dc:description`` (abstract). This method primarily fills in the
        full author list (the search API only returns ``dc:creator`` — first
        author). Abstract retrieval is attempted for records still missing
        one, but the hit rate is typically low.
        """
        need = [r for r in records if not r.abstract and (r.doi or r.source_id)]
        if not need:
            return
        log.info(f"Scopus: enriching {len(need)} records via Abstract Retrieval API "
                 f"(author lists + abstract attempt)")

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

        log.info(f"Scopus enrichment done: {fetched} abstracts, "
                 f"{authors_filled} full author lists, "
                 f"{failed} unavailable out of {len(need)} attempted. "
                 f"Records still missing abstracts will be handled by "
                 f"cross-database abstract recovery.")

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
        # Scopus sometimes returns a single-author "author" field as a bare
        # dict instead of a list-of-dicts; normalize before iterating or
        # ``a.get(...)`` below throws AttributeError on dict keys (strings).
        author_list = e.get("author", [])
        if isinstance(author_list, dict):
            author_list = [author_list]
        if author_list:
            authors = [
                a.get("authname", "") for a in author_list
                if isinstance(a, dict) and a.get("authname")
            ]
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
            doi=_normalize_doi(e.get("prism:doi")),
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


def _read_records_csv(path: Path) -> list[Record]:
    """Load a CSV file written by _write_csv back into Record objects."""
    records: list[Record] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                records.append(Record(
                    source_db=row.get("source_db", ""),
                    source_id=row.get("source_id", ""),
                    doi=_normalize_doi(row.get("doi")),
                    title=row.get("title", ""),
                    abstract=row.get("abstract", ""),
                    authors=[a.strip() for a in row.get("authors", "").split("; ") if a.strip()],
                    journal=row.get("journal", ""),
                    year=int(row["year"]) if row.get("year") else None,
                    pub_date=row.get("pub_date", ""),
                    keywords=[k.strip() for k in row.get("keywords", "").split("; ") if k.strip()],
                    mesh_terms=[m.strip() for m in row.get("mesh_terms", "").split("; ") if m.strip()],
                    pub_types=[p.strip() for p in row.get("pub_types", "").split("; ") if p.strip()],
                    url=row.get("url", ""),
                    volume=row.get("volume", ""),
                    issue=row.get("issue", ""),
                    pages=row.get("pages", ""),
                    isbn=row.get("isbn", ""),
                    issn=row.get("issn", ""),
                ))
            except Exception:
                log.warning(f"Could not parse row from {path.name}: {row.get('source_id', '?')}")
    return records


def _import_ebsco_csv(path: Path) -> list[Record]:
    """Import an EBSCOhost CSV export and convert to Record objects.

    Handles exports from APA PsycInfo (shortDBName=psyh) and
    APA PsycArticles (shortDBName=pdh). Both are mapped to
    source_db="psycinfo" for dedup purposes.
    """
    records: list[Record] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                db_name = row.get("longDBName", "") or row.get("shortDBName", "")
                # Normalize to a single source_db label
                source_db = "psycinfo"

                # Accession number as stable ID
                an = row.get("an", "")

                # Title
                title = row.get("title", "") or ""

                # Abstract
                abstract = row.get("abstract", "") or ""

                # Year from publicationDate (YYYYMMDD) or coverDate
                year = None
                pub_date = row.get("publicationDate", "") or row.get("coverDate", "") or ""
                if pub_date:
                    try:
                        year = int(pub_date[:4])
                    except ValueError:
                        pass

                # Authors: semicolon-separated, "Last, First M." format
                authors: list[str] = []
                contributors = row.get("contributors", "") or ""
                if contributors:
                    authors = [a.strip() for a in contributors.split(";") if a.strip()]

                # Journal
                journal = row.get("source", "") or ""

                # DOI
                doi = _normalize_doi(row.get("doi"))

                # ISSN / ISBN
                issn = row.get("issns", "") or ""
                isbn = row.get("isbns", "") or ""

                # Volume / Issue / Pages
                volume = row.get("volume", "") or ""
                issue = row.get("issue", "") or ""
                page_start = row.get("pageStart", "") or ""
                page_end = row.get("pageEnd", "") or ""
                pages = f"{page_start}-{page_end}" if page_start and page_end else (page_start or page_end or "")

                # Keywords: semicolon-separated subjects
                keywords: list[str] = []
                subjects = row.get("subjects", "") or ""
                if subjects:
                    keywords = [s.strip() for s in subjects.split(";") if s.strip()]

                # Publication types
                pub_types: list[str] = []
                pub_types_str = row.get("pubTypes", "") or ""
                if pub_types_str:
                    pub_types = [p.strip() for p in pub_types_str.split(";") if p.strip()]

                # URL
                url = row.get("plink", "") or ""

                records.append(Record(
                    source_db=source_db,
                    source_id=an,
                    doi=doi,
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    journal=journal,
                    year=year,
                    pub_date=pub_date,
                    keywords=keywords,
                    pub_types=pub_types,
                    url=url,
                    volume=volume,
                    issue=issue,
                    pages=pages,
                    isbn=isbn,
                    issn=issn,
                ))
            except Exception:
                log.warning(f"Could not parse EBSCO row from {path.name}: {row.get('an', '?')}")

    return records


def _import_ris(path: Path, source_db: str) -> list[Record]:
    """Import a RIS file and convert to Record objects.

    The ``source_db`` parameter sets the source_db field for all records
    (e.g. "wos" for WoS manual RIS exports).
    """
    records: list[Record] = []
    current: dict[str, list[str]] = {}

    def _flush() -> Record | None:
        """Build a Record from the accumulated current dict."""
        if not current:
            return None
        title = " ".join(current.get("TI", []))
        if not title.strip():
            return None

        authors = current.get("AU", [])
        journal = " ".join(current.get("T2", []) or current.get("JO", []))
        doi = _normalize_doi(" ".join(current.get("DO", [])).strip() or None)
        abstract = " ".join(current.get("AB", []))
        keywords = current.get("KW", [])

        year = None
        py_list = current.get("PY", [])
        if py_list:
            try:
                year = int(py_list[0].strip()[:4])
            except ValueError:
                pass

        volume = " ".join(current.get("VL", []))
        issue = " ".join(current.get("IS", []))
        sp = " ".join(current.get("SP", []))
        ep = " ".join(current.get("EP", []))
        pages = f"{sp}-{ep}" if sp and ep else (sp or ep)
        url = " ".join(current.get("UR", []))
        issn = " ".join(current.get("SN", []))

        # Prefer stable accession IDs (WoS AN / UT) over DOI/title prefixes.
        an = " ".join(current.get("AN", [])).strip()
        ut = " ".join(current.get("UT", [])).strip()
        if an:
            source_id = an
        elif ut:
            source_id = ut
        elif doi:
            source_id = f"doi:{doi}"
        else:
            # Full-title hash avoids collisions from title[:50] truncation.
            title_key = hashlib.md5(title.lower().encode("utf-8")).hexdigest()[:16]
            source_id = f"title:{title_key}"

        return Record(
            source_db=source_db,
            source_id=source_id,
            doi=doi,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            year=year,
            pub_date=" ".join(py_list),
            keywords=keywords,
            url=url,
            volume=volume,
            issue=issue,
            pages=pages,
            issn=issn,
        )

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if line.startswith("ER  ") or line == "ER  -":
                rec = _flush()
                if rec:
                    records.append(rec)
                current = {}
            elif len(line) >= 6 and line[2:4] == "  ":
                tag = line[:2]
                value = line[6:].strip()
                current.setdefault(tag, []).append(value)

        # Flush trailing record if file doesn't end with ER
        rec = _flush()
        if rec:
            records.append(rec)

    return records


def _guess_ris_source_db(stem: str) -> str:
    """Map a RIS filename stem to a canonical source_db label."""
    stem_lower = stem.lower()
    if (stem_lower.startswith("savedrecs")
            or "wos" in stem_lower
            or "web_of_science" in stem_lower
            or "webofscience" in stem_lower):
        return "wos"
    if "psycinfo" in stem_lower or "ebsco" in stem_lower:
        return "psycinfo"
    if "scopus" in stem_lower:
        return "scopus"
    return stem


def _record_completeness(r: Record) -> tuple:
    """Sort key for choosing the best representative in a duplicate group."""
    return (
        1 if (r.abstract or "").strip() else 0,
        len(r.abstract or ""),
        len(r.title or ""),
        len(r.authors or []),
        1 if r.source_db == "pubmed" else 0,
        r.year or 0,
    )


def _merge_record_fields(keeper: Record, donors: list[Record]) -> Record:
    """Fill missing/short fields on keeper from donor siblings (same DOI group)."""
    for d in sorted(donors, key=_record_completeness, reverse=True):
        if len((keeper.title or "").strip()) < max(20, len((d.title or "").strip()) // 2):
            if (d.title or "").strip():
                keeper.title = d.title
        # Upgrade, not just fill: a short/truncated abstract should lose to
        # a substantially longer one from a sibling, not just an empty one
        # (previously only fired when keeper.abstract was empty, which let
        # a heavily truncated abstract "win" over full-length siblings).
        keeper_abstract = (keeper.abstract or "").strip()
        donor_abstract = (d.abstract or "").strip()
        if donor_abstract and (
            not keeper_abstract or len(keeper_abstract) < len(donor_abstract) // 2
        ):
            keeper.abstract = d.abstract
        if not keeper.authors and d.authors:
            keeper.authors = list(d.authors)
        if not keeper.journal and d.journal:
            keeper.journal = d.journal
        if not keeper.doi and d.doi:
            keeper.doi = d.doi
        if not keeper.year and d.year:
            keeper.year = d.year
        if not keeper.pages and d.pages:
            keeper.pages = d.pages
        if not keeper.volume and d.volume:
            keeper.volume = d.volume
    return keeper


def _collapse_exact_dois(
    records: list[Record],
) -> tuple[list[Record], dict[str, int], list[dict], set[str]]:
    """Deterministic exact-DOI merge before fuzzy ASySD matching.

    Returns (collapsed_records, stats, doi_title_conflicts, protected_ids).

    ``protected_ids`` are namespaced ``source_db:source_id`` identifiers for
    every record in a DOI group with a gross title conflict. Downstream
    fuzzy matching (ASySD) must treat these as quarantined — never silently
    auto-merge them — since they need human review (same-paper metadata
    variant, erratum/original pair, or a genuine DOI collision).
    """
    by_doi: dict[str, list[Record]] = {}
    no_doi: list[Record] = []
    invalid_cleared = 0
    for r in records:
        raw = (r.doi or "").strip()
        norm = _normalize_doi(raw)
        if raw and not norm:
            r.doi = None
            invalid_cleared += 1
            no_doi.append(r)
            continue
        if not norm:
            no_doi.append(r)
            continue
        r.doi = norm  # canonical lowercase form
        by_doi.setdefault(norm, []).append(r)

    conflicts: list[dict] = []
    protected_ids: set[str] = set()
    collapsed: list[Record] = list(no_doi)
    merged_groups = 0
    records_removed = 0

    for doi, group in by_doi.items():
        if len(group) == 1:
            collapsed.append(group[0])
            continue

        # Erratum / correction detection: if any record in this same-DOI
        # group has an erratum/correction/corrigendum/retraction marker in
        # its title, do NOT collapse.  These are distinct publications
        # (the original article and the notice about it) that happen to
        # share a DOI.  Collapsing them silently drops the original behind
        # the erratum stub.  Route to protected_ids so ASySD also treats
        # them as quarantined (demoted to maybe-pairs).
        has_erratum = any(_is_erratum_title(g.title) for g in group)
        if has_erratum:
            log.info(
                "erratum/correction group skipped collapse: DOI=%s n=%d titles=%s",
                doi, len(group), [g.title[:120] for g in group],
            )
            collapsed.extend(group)
            for g in group:
                protected_ids.add(_namespaced_id(g.source_db, g.source_id))
            conflicts.append({
                "doi": doi,
                "title1": next((g.title[:120] for g in group
                                if _is_erratum_title(g.title)), ""),
                "title2": next((g.title[:120] for g in group
                                if not _is_erratum_title(g.title)), ""),
                "source_db1": "",
                "source_id1": "",
                "source_db2": "",
                "source_id2": "",
                "conflict_type": "doi_erratum",
            })
            continue

        # Gross title conflict → keep all, flag for review
        titled = [(g, g.title.strip()) for g in group if (g.title or "").strip()]
        conflict = False
        for i in range(len(titled)):
            for j in range(i + 1, len(titled)):
                t1, t2 = titled[i][1], titled[j][1]
                if len(t1) >= 20 and len(t2) >= 20 and _title_token_jaccard(t1, t2) < 0.4:
                    conflict = True
                    g1, g2 = titled[i][0], titled[j][0]
                    conflicts.append({
                        "doi": doi,
                        "title1": t1[:120],
                        "title2": t2[:120],
                        "source_db1": g1.source_db,
                        "source_id1": g1.source_id,
                        "source_db2": g2.source_db,
                        "source_id2": g2.source_id,
                        "conflict_type": "title_jaccard",
                    })
        if conflict:
            collapsed.extend(group)
            for g in group:
                protected_ids.add(_namespaced_id(g.source_db, g.source_id))
            continue
        best = max(group, key=_record_completeness)
        best = _merge_record_fields(best, group)
        collapsed.append(best)
        merged_groups += 1
        records_removed += len(group) - 1

    stats = {
        "exact_doi_groups_merged": merged_groups,
        "exact_doi_records_removed": records_removed,
        "exact_doi_title_conflicts": len(conflicts),
        "invalid_dois_cleared": invalid_cleared,
    }
    log.info(
        f"Exact-DOI collapse: {merged_groups} groups merged "
        f"(-{records_removed} records), {len(conflicts)} title conflicts kept separate "
        f"({len(protected_ids)} records protected from further auto-merge), "
        f"{invalid_cleared} invalid DOIs cleared"
    )
    return collapsed, stats, conflicts, protected_ids


def _collect_all_sources(search_dir: Path) -> tuple[list[Record], dict[str, list[Record]], dict[str, int]]:
    """Discover and load all data sources from a search directory.

    Returns (all_records, all_records_by_db, per_db_counts).
    """
    all_records: list[Record] = []
    all_records_by_db: dict[str, list[Record]] = {}
    per_db: dict[str, int] = {}

    # 1. Load raw_*.csv files (API exports in Record schema)
    # Skip mislabeled WoS leftovers (raw_savedrecs*.csv) — prefer re-import
    # from RIS with corrected source_db=wos when RIS files are present.
    raw_csvs = sorted(search_dir.glob("raw_*.csv"))
    ris_present = any(
        p.name != "records_deduplicated.ris" for p in search_dir.glob("*.ris")
    )
    for csv_path in raw_csvs:
        db_name = csv_path.stem.replace("raw_", "")  # e.g. "pubmed", "scopus"
        if ris_present and db_name.startswith("savedrecs"):
            log.info(f"Skipping {csv_path.name}: will re-import WoS from RIS as source_db=wos")
            continue
        recs = _read_records_csv(csv_path)
        if recs:
            all_records_by_db[db_name] = recs
            per_db[db_name] = len(recs)
            all_records.extend(recs)
            log.info(f"Loaded {len(recs)} records from {csv_path.name} (db={db_name})")
        else:
            log.info(f"Skipping empty raw CSV: {csv_path.name}")

    # Snapshot of which databases already have real data from raw CSVs.
    # Used to skip re-import of manual export files on subsequent dedup runs.
    dbs_from_raw_csv = {db for db, recs in all_records_by_db.items() if recs}

    # 2. Import EBSCO CSV exports (EBSCOhost format)
    ebsco_csvs = sorted(search_dir.glob("EBSCO*.csv")) + sorted(search_dir.glob("ebsco*.csv"))
    seen_ebsco_ids: set[str] = set()
    psycinfo_recs: list[Record] = []
    for csv_path in ebsco_csvs:
        # Skip files that look like raw_* CSVs we already handled
        if csv_path.name.startswith("raw_"):
            continue
        # Skip EBSCO CSVs when raw_psycinfo.csv already had data from a prior run
        if "psycinfo" in dbs_from_raw_csv:
            log.info(f"Skipping {csv_path.name}: raw_psycinfo.csv already has "
                     f"{len(all_records_by_db['psycinfo'])} records")
            continue
        recs = _import_ebsco_csv(csv_path)
        new = 0
        for r in recs:
            if r.source_id not in seen_ebsco_ids:
                seen_ebsco_ids.add(r.source_id)
                psycinfo_recs.append(r)
                new += 1
        log.info(f"Imported {len(recs)} records from {csv_path.name} "
                 f"({new} new, {len(recs) - new} duplicate within EBSCO files)")

    if psycinfo_recs:
        db_name = "psycinfo"
        all_records_by_db[db_name] = psycinfo_recs
        per_db[db_name] = len(psycinfo_recs)
        all_records.extend(psycinfo_recs)
        log.info(f"Total psycinfo records after dedup within EBSCO files: {len(psycinfo_recs)}")

    # 3. Import RIS files (manual exports from WoS or other DBs).
    # Skip RIS files only when the corresponding raw CSV already had data
    # (from a prior dedup run), not when the db was just populated by another
    # RIS file in the same batch.
    ris_files = sorted(search_dir.glob("*.ris"))
    for ris_path in ris_files:
        # Skip our own deduplicated export
        if ris_path.name == "records_deduplicated.ris":
            continue
        ris_db = _guess_ris_source_db(ris_path.stem)

        recs = _import_ris(ris_path, ris_db)
        if recs:
            # Skip RIS files when raw CSV for the same db already had data
            # from a prior dedup run (not from another RIS file in this batch).
            if ris_db in dbs_from_raw_csv:
                log.info(f"Skipping {ris_path.name}: raw_{ris_db}.csv already has "
                         f"{len(all_records_by_db[ris_db])} records")
                continue
            # If we already have records for this db from another RIS file, append
            if ris_db in all_records_by_db:
                all_records_by_db[ris_db].extend(recs)
                per_db[ris_db] = per_db.get(ris_db, 0) + len(recs)
            else:
                all_records_by_db[ris_db] = recs
                per_db[ris_db] = len(recs)
            all_records.extend(recs)
            log.info(f"Imported {len(recs)} records from {ris_path.name} (db={ris_db})")

    return all_records, all_records_by_db, per_db



def _run_deduplication(all_records: list[Record], search_dir: Path) -> tuple[list[Record], dict[str, int]]:
    """Run deduplication on the combined record pool.

    Returns (deduped_records, dedup_stats).
    """
    original_raw_count = len(all_records)
    log.info(f"Total raw records across all sources: {original_raw_count}")
    log.info(f"Deduplication method: {DEDUP_METHOD}")

    maybe_pairs_data = []
    exact_doi_stats: dict[str, int] = {}

    # Deterministic exact-DOI merge before fuzzy matching
    all_records, exact_doi_stats, doi_conflicts, protected_ids = _collapse_exact_dois(all_records)
    conflicted_dois = {row["doi"] for row in doi_conflicts}
    if doi_conflicts:
        conflict_path = search_dir / "doi_title_conflicts.csv"
        with open(conflict_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(doi_conflicts[0].keys()))
            w.writeheader()
            for row in doi_conflicts:
                w.writerow(row)
        log.info(f"Wrote {len(doi_conflicts)} DOI/title conflicts -> {conflict_path}")

    if DEDUP_METHOD == "asysd" and deduplicate_asysd is not None:
        # Pre-normalize for ASySD (hyphen/author cleanup). record_id is
        # namespaced as source_db:source_id so PubMed/EuropePMC PMIDs do not
        # collide as graph nodes.
        asysd_input = []
        record_by_id: dict[str, Record] = {}
        asysd_protected_ids: set[str] = set()
        for r in all_records:
            base_rid = _namespaced_id(r.source_db, r.source_id)
            rid = base_rid
            n = 2
            while rid in record_by_id:
                rid = f"{base_rid}#{n}"
                n += 1
            record_by_id[rid] = r
            if base_rid in protected_ids:
                asysd_protected_ids.add(rid)
            title_norm = " ".join(r.title.replace("-", " ").split())
            abstract_norm = (
                " ".join(r.abstract.replace("-", " ").split()) if r.abstract else ""
            )
            author_str = "; ".join(r.authors) if r.authors else None
            if author_str:
                author_str = " ".join(author_str.replace(".", " ").split())
            asysd_input.append({
                "source": r.source_db,
                "record_id": rid,
                "author": author_str,
                "title": title_norm,
                "year": str(r.year) if r.year else None,
                "journal": r.journal,
                "abstract": abstract_norm,
                "doi": r.doi,
                "pages": r.pages or None,
                "volume": r.volume or None,
                "number": r.issue or None,
                "isbn": r.isbn or None,
                "label": r.source_db,
            })

        asysd_unique, asysd_stats, maybe_pairs_data = deduplicate_asysd(
            asysd_input, keep_source="pubmed", protected_ids=asysd_protected_ids
        )

        deduped: list[Record] = []
        missing_ids: list[str] = []
        for rec_dict in asysd_unique:
            rid = rec_dict.get("record_id", "")
            if rid in record_by_id:
                deduped.append(record_by_id[rid])
            else:
                dup_id = rec_dict.get("duplicate_id", "")
                if dup_id in record_by_id:
                    deduped.append(record_by_id[dup_id])
                else:
                    missing_ids.append(rid or dup_id or "?")

        if missing_ids:
            log.error(
                f"ASySD remap failed for {len(missing_ids)} record(s); "
                f"sample IDs: {missing_ids[:10]}"
            )
            raise RuntimeError(
                f"ASySD→Record remap lost {len(missing_ids)} records "
                f"(asysd_unique={len(asysd_unique)}, mapped={len(deduped)})"
            )
        if len(deduped) != asysd_stats["unique"]:
            raise RuntimeError(
                f"ASySD unique count mismatch: asysd={asysd_stats['unique']} "
                f"mapped={len(deduped)}"
            )

        # Fill truncated/missing fields from same-DOI siblings in the
        # post-exact-DOI pool (helps PubMed titles truncated in stored CSV).
        # Skip DOIs quarantined as title conflicts: those siblings are kept
        # separate on purpose and must not bleed fields into each other.
        by_doi: dict[str, list[Record]] = {}
        for r in all_records:
            d = _normalize_doi(r.doi)
            if d:
                by_doi.setdefault(d, []).append(r)
        for survivor in deduped:
            d = _normalize_doi(survivor.doi)
            if d and d in by_doi and d not in conflicted_dois:
                _merge_record_fields(survivor, by_doi[d])

        dedup_stats = {
            "total_raw": original_raw_count,
            "unique": len(deduped),
            "duplicates_removed": original_raw_count - len(deduped),
            "method": "asysd",
            "asysd_unique": asysd_stats["unique"],
            "asysd_duplicates_removed": asysd_stats["duplicates_removed"],
            **exact_doi_stats,
        }
        if (
            dedup_stats["unique"] + dedup_stats["duplicates_removed"]
            != dedup_stats["total_raw"]
        ):
            raise RuntimeError(
                f"Dedup arithmetic broken: unique({dedup_stats['unique']}) + "
                f"removed({dedup_stats['duplicates_removed']}) != "
                f"raw({dedup_stats['total_raw']})"
            )

        if maybe_pairs_data:
            maybe_path = search_dir / "maybe_pairs.csv"
            with open(maybe_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(maybe_pairs_data[0].keys()))
                w.writeheader()
                for row in maybe_pairs_data:
                    w.writerow(row)
            log.info(f"Wrote {len(maybe_pairs_data)} maybe-pairs -> {maybe_path}")

    else:
        if DEDUP_METHOD == "asysd" and deduplicate_asysd is None:
            log.warning(
                "ASySD dedup not available (dedup_asysd module not found), "
                "falling back to simple dedup"
            )
        deduped, dedup_stats = deduplicate_simple(all_records)
        dedup_stats["method"] = "simple"
        dedup_stats["total_raw"] = original_raw_count
        dedup_stats["unique"] = len(deduped)
        dedup_stats["duplicates_removed"] = original_raw_count - len(deduped)
        dedup_stats.update(exact_doi_stats)

    log.info(
        f"After dedup: {len(deduped)} unique records "
        f"({dedup_stats['duplicates_removed']} duplicates removed)"
    )

    return deduped, dedup_stats



def export_results(records: list[Record],
                   all_records_by_db: dict[str, list[Record]],
                   queries: dict[str, str],
                   per_db_counts: dict[str, int],
                   dedup_stats: dict[str, int],
                   output_dir: Path,
                   search_mode: str,
                   search_start_year: int | None,
                   search_end_date: str) -> None:
    """Writes all PRISMA-required artifacts to output_dir."""

    # 1. Per-database raw CSVs (pre-dedup, for auditability)
    for db_name, db_records in all_records_by_db.items():
        raw_path = output_dir / f"raw_{db_name}.csv"
        _write_csv(db_records, raw_path)
        log.info(f"Wrote {len(db_records)} raw records from {db_name} -> {raw_path}")

    # 2. Deduplicated CSV
    csv_path = output_dir / "records_deduplicated.csv"
    _write_csv(records, csv_path)
    log.info(f"Wrote {len(records)} deduplicated records -> {csv_path}")

    # 3. RIS export for Rayyan / ASReview / Covidence / EndNote
    ris_path = output_dir / "records_deduplicated.ris"
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
    if search_mode == "os_validation":
        search_scope_note = (
            "OS validation mode approximates the Boeckle et al. (2016) search "
            "terms and end date for pipeline validation only. It is not the "
            "expanded production search strategy."
        )
        filters_applied = {
            "language": "English in non-PubMed API queries where supported",
            "date": f"inception to {search_end_date}",
            "screening_filters": (
                "Human/adult/primary research criteria are applied during "
                "screening to stay close to the original study workflow."
            ),
        }
    elif search_mode == "os_table_recall":
        search_scope_note = (
            "Table-recall mode uses broadened search terms to maximise "
            "recovery of the 49 studies in Boeckle et al. Table 1. Language "
            "filters are NOT applied at the search stage; apply English-"
            "language screening downstream to match the original workflow."
        )
        filters_applied = {
            "language": "None at search stage — apply during screening",
            "date": f"inception to {search_end_date}",
            "screening_filters": (
                "Language (English), human/adult, and primary-research "
                "criteria should all be applied during screening."
            ),
        }
    elif search_mode == "ludwig_validation":
        search_scope_note = (
            "Ludwig validation mode replicates the search strategy from "
            "Ludwig et al. (2018) Lancet Psychiatry (trauma/stressors in "
            "FND). Uses a 3-block AND query: FND terms x stressor terms x "
            "study-design terms. Date range: inception to 2016/11/04. "
            "Language filters are NOT applied at search stage."
        )
        filters_applied = {
            "language": "None at search stage — apply during screening",
            "date": f"inception to {search_end_date}",
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

    # Determine which databases were automated vs manual
    automated_dbs = [k for k in queries.keys() if k != "ebsco_psycinfo"]
    manual_dbs = []
    # EBSCO PsycInfo: show as not automated only if not already imported
    if "ebsco_psycinfo" in queries and "psycinfo" not in per_db_counts:
        manual_dbs.append(
            "APA PsycInfo / PsycArticles (EBSCOhost) — query in ebsco_psycinfo; "
            "export manually from web UI with date filter applied"
        )
    # Any additional dbs in per_db that aren't in queries are manual imports
    # (skip psycinfo — it corresponds to ebsco_psycinfo query)
    for db in per_db_counts:
        if db not in queries and db != "psycinfo":
            manual_dbs.append(f"{db} (manual import)")

    # De-duplicate database names: ebsco_psycinfo (query name) and
    # psycinfo (imported db) refer to the same source.
    db_names = set(per_db_counts.keys())
    db_names.update(k for k in queries.keys() if k != "ebsco_psycinfo")
    if "ebsco_psycinfo" in queries and "psycinfo" not in per_db_counts:
        db_names.add("ebsco_psycinfo")

    # Count records missing abstracts (per-database and total)
    missing_abstracts: dict[str, int] = {}
    for r in records:
        if not r.abstract.strip():
            missing_abstracts[r.source_db] = missing_abstracts.get(r.source_db, 0) + 1
    total_missing = sum(missing_abstracts.values())

    prisma_meta = {
        "run_id": output_dir.name,
        "search_mode": search_mode,
        "search_profile": _search_profiles.get(
            search_mode, "expanded FND neuroimaging protocol"
        ),
        "search_date": datetime.now(timezone.utc).isoformat(),
        "search_range": (
            f"{search_start_year}-01-01 to {search_end_date}"
            if search_start_year else f"inception to {search_end_date}"
        ),
        "databases_searched": sorted(db_names),
        "databases_not_automated": manual_dbs,
        "queries": queries,
        "records_per_database": per_db_counts,
        "deduplication": dedup_stats,
        "abstracts_missing": {
            "total": total_missing,
            "total_records": len(records),
            "percent": round(total_missing / len(records) * 100, 1) if records else 0,
            "by_database": missing_abstracts,
        },
        "filters_applied": filters_applied,
        "notes": search_scope_note,
    }
    meta_path = output_dir / "prisma_search_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(prisma_meta, f, indent=2)
    log.info(f"Wrote PRISMA metadata -> {meta_path}")
    if total_missing > 0:
        log.warning(f"Records missing abstracts: {total_missing}/{len(records)} ({total_missing/len(records)*100:.1f}%)")
        for db, n in sorted(missing_abstracts.items()):
            db_total = per_db_counts.get(db, 0)
            log.warning(f"  {db}: {n}/{db_total} missing ({n/db_total*100:.1f}%)" if db_total else f"  {db}: {n} missing")


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
# ABSTRACT RECOVERY (cross-database, pre-dedup)
# ---------------------------------------------------------------------------

def _recover_abstracts(records: list[Record]) -> None:
    """Recover empty abstracts via PubMed efetch, PubMed title search, and EuropePMC.

    Runs after all databases are fetched and Scopus enrichment is done,
    but BEFORE deduplication so the dedup matcher has maximum text.

    Strategy (in order, first hit wins):
      1. PubMed efetch by PMID — for PubMed records without an abstract.
      2. PubMed title search → efetch — gated by title Jaccard similarity.
      3. EuropePMC title search — gated by title Jaccard similarity.
    """
    need = [r for r in records if not r.abstract]
    if not need:
        return
    log.info(f"Abstract recovery: {len(need)} records with empty abstracts. "
             f"Attempting PubMed + EuropePMC title search...")

    EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    headers = {"User-Agent": "FND-MetaAnalysis-Research/1.0 (academic research)"}
    min_sim = 0.5

    def _fetch_url(url: str, timeout: int = 15) -> tuple[str, int | None]:
        try:
            req = requests.get(url, headers=headers, timeout=timeout)
            return req.text, req.status_code
        except requests.RequestException as e:
            return str(e), None

    def _pubmed_efetch_record(pmid: str) -> tuple[str | None, str | None]:
        url = (f"{EUTILS}/efetch.fcgi?db=pubmed&id={pmid}"
               f"&rettype=abstract&retmode=xml")
        text, status = _fetch_url(url)
        if status != 200:
            return None, None
        root = ET.fromstring(text)
        title = _element_text(root.find(".//ArticleTitle"))
        parts = [_element_text(e) for e in root.findall(".//Abstract/AbstractText")]
        abstract = _strip_html(" ".join(parts)) if parts else None
        return abstract, title

    def _pubmed_title_search(title: str, year: str | None) -> tuple[str | None, str]:
        query = f'"{title[:200]}"'
        if year:
            query += f" AND {year}[pdat]"
        from urllib.parse import quote
        url = (f"{EUTILS}/esearch.fcgi?db=pubmed&term={quote(query)}"
               f"&retmode=json&retmax=3")
        text, status = _fetch_url(url)
        if status != 200:
            return None, "pubmed_title"
        try:
            ids = json.loads(text).get("esearchresult", {}).get("idlist", [])
            for pmid in ids:
                time.sleep(0.35)
                abstract, hit_title = _pubmed_efetch_record(pmid)
                if not abstract:
                    continue
                sim = _title_token_jaccard(title, hit_title or "")
                if sim >= min_sim or not (hit_title or "").strip():
                    return abstract, f"pubmed_title:{pmid}:sim={sim:.2f}"
        except (json.JSONDecodeError, KeyError):
            pass
        return None, "pubmed_title"

    def _epmc_title_search(title: str, year: str | None) -> tuple[str | None, str]:
        from urllib.parse import quote
        query = f'title:"{title[:200]}"'
        if year:
            query += f" AND PUB_YEAR:{year}"
        url = (f"{EPMC}?query={quote(query)}"
               f"&format=json&pageSize=3&resultType=core")
        text, status = _fetch_url(url)
        if status != 200:
            return None, "europepmc_title"
        try:
            results = (json.loads(text)
                       .get("resultList", {})
                       .get("result", []))
            for hit in results:
                abstract = hit.get("abstractText", "")
                if not abstract:
                    continue
                hit_title = _strip_html(hit.get("title", "") or "")
                sim = _title_token_jaccard(title, hit_title)
                if sim >= min_sim or not hit_title.strip():
                    return (
                        _strip_html(abstract),
                        f"europepmc_title:{hit.get('id', '?')}:sim={sim:.2f}",
                    )
        except (json.JSONDecodeError, KeyError):
            pass
        return None, "europepmc_title"

    recovered = 0
    for i, rec in enumerate(need, 1):
        abstract = None
        provenance = ""

        if rec.source_db == "pubmed" and rec.source_id:
            pmid = rec.source_id
            abstract, _hit_title = _pubmed_efetch_record(pmid)
            if abstract:
                provenance = f"pubmed_efetch:{pmid}"
            time.sleep(0.35)

        if not abstract and (rec.title or "").strip():
            abstract, provenance = _pubmed_title_search(
                rec.title, str(rec.year) if rec.year else None
            )
            time.sleep(0.35)

        if not abstract and (rec.title or "").strip():
            abstract, provenance = _epmc_title_search(
                rec.title, str(rec.year) if rec.year else None
            )
            time.sleep(0.5)

        if abstract:
            rec.abstract = abstract
            recovered += 1
            log.debug(
                f"  [{i}/{len(need)}] recovered via {provenance}: {rec.title[:60]}"
            )
        else:
            log.debug(f"  [{i}/{len(need)}] not found: {rec.title[:60]}")

        if i % 50 == 0:
            log.info(
                f"  Abstract recovery progress: {i}/{len(need)} "
                f"(recovered={recovered})"
            )

    log.info(
        f"Abstract recovery done: {recovered}/{len(need)} recovered "
        f"({100 * recovered / len(need):.0f}%)"
    )



# ---------------------------------------------------------------------------
# PHASE 1: SEARCH
# ---------------------------------------------------------------------------

def run_searches() -> tuple[list[Record], dict[str, list[Record]], dict[str, int], dict[str, str]]:
    """Execute API searches across all configured databases.

    Returns (all_records, all_records_by_db, per_db_counts, queries).
    Raw CSVs are NOT written here — that happens in export_results after dedup
    (or in run_dedup for the two-phase workflow).
    """
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
        "pubmed":         build_pubmed_query(),
        "europepmc":      build_europepmc_query(),
        "wos":            build_wos_query(),
        "scopus":         build_scopus_query(),
        "ebsco_psycinfo": build_ebsco_psycinfo_query(),
        "_search_mode":   SEARCH_MODE,
        "_search_start_year": SEARCH_START_YEAR,
        "_search_end_date": SEARCH_END_DATE,
    }

    with open(OUTPUT_DIR / "queries.json", "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)
    with open(OUTPUT_DIR / "queries.txt", "w", encoding="utf-8") as f:
        for db, q in queries.items():
            f.write(f"--- {db} ---\n{q}\n\n")
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
    log.info("Search results summary (API databases):")
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
    # When dedup will run in the same session (default mode), enrich Scopus
    # records now so the dedup matcher has real author/abstract data.
    # In --no-dedup mode, we still offer enrichment so the raw CSVs are as
    # complete as possible.
    if (scopus_abstracts_fetched or AUTO_MODE):
        scopus_all = [r for r in all_records if r.source_db == "scopus"]
        if scopus_all:
            need = [r for r in scopus_all if not r.abstract]
            if need:
                log.info(f"Enriching Scopus records: {len(need)}/{len(scopus_all)} "
                         f"missing abstracts (full author lists harvested from the same calls)")
                ScopusClient()._enrich_abstracts(scopus_all)

    # -- Cross-database abstract recovery (pre-dedup) -----------------------
    if SKIP_ABSTRACT_RECOVERY:
        log.info("Skipping abstract recovery (--skip-abstract-recovery)")
    else:
        _recover_abstracts(all_records)

    return all_records, all_records_by_db, per_db, queries


# ---------------------------------------------------------------------------
# PHASE 2: DEDUP
# ---------------------------------------------------------------------------

def run_dedup(search_dir: Path) -> None:
    """Load all sources from a search directory, deduplicate, and export.

    This is the entry point for --dedup <dir> mode. It discovers:
      - raw_*.csv files (API exports in Record schema)
      - EBSCO*.csv / ebsco*.csv files (EBSCOhost manual exports)
      - *.ris files (WoS or other manual RIS exports, except records_deduplicated.ris)
    """
    log.info(f"Dedup-only mode on directory: {search_dir.resolve()}")

    # Load queries from the search phase (for PRISMA metadata)
    queries_path = search_dir / "queries.json"
    queries: dict[str, str] = {}
    _search_mode_from_queries = ""
    _search_start_year_from_queries: int | None = None
    _search_end_date_from_queries = ""
    if queries_path.exists():
        with open(queries_path, "r", encoding="utf-8") as f:
            raw_queries = json.load(f)
        # Extract metadata keys (prefixed with _) before using as db queries
        _search_mode_from_queries = raw_queries.pop("_search_mode", "")
        _search_start_year_from_queries = raw_queries.pop("_search_start_year", None)
        _search_end_date_from_queries = raw_queries.pop("_search_end_date", "")
        queries = raw_queries
        log.info(f"Loaded queries.json ({len(queries)} databases, mode={_search_mode_from_queries})")
    else:
        log.warning("queries.json not found — PRISMA metadata will not include query strings")

    # Prefer metadata from queries.json (written during search phase),
    # fall back to existing prisma_search_metadata.json if queries.json is missing.
    search_mode = _search_mode_from_queries
    search_start_year = _search_start_year_from_queries
    search_end_date = _search_end_date_from_queries

    if not search_mode:
        existing_meta_path = search_dir / "prisma_search_metadata.json"
        if existing_meta_path.exists():
            try:
                with open(existing_meta_path, "r", encoding="utf-8") as f:
                    existing_meta = json.load(f)
                search_mode = existing_meta.get("search_mode", "")
                search_range = existing_meta.get("search_range", "inception to ")
                if "inception" not in search_range and " to " in search_range:
                    parts = search_range.split(" to ")
                    try:
                        search_start_year = int(parts[0][:4])
                    except ValueError:
                        pass
                    search_end_date = parts[1]
                else:
                    search_end_date = search_range.replace("inception to ", "")
                log.info(f"Loaded existing metadata: mode={search_mode}, range={search_range}")
            except (json.JSONDecodeError, KeyError):
                log.warning("Could not parse existing prisma_search_metadata.json")

    # Collect all data sources
    all_records, all_records_by_db, per_db = _collect_all_sources(search_dir)

    if not all_records:
        log.error("No records found in any source file. Aborting.")
        return

    # Report what was found
    log.info("=" * 60)
    log.info("Sources discovered:")
    for db, n in per_db.items():
        log.info(f"  {db}: {n} records")
    log.info(f"  TOTAL: {len(all_records)} raw records across {len(per_db)} databases")
    log.info("=" * 60)

    # -- Cross-database abstract recovery (pre-dedup) -----------------------
    if SKIP_ABSTRACT_RECOVERY:
        log.info("Skipping abstract recovery (--skip-abstract-recovery)")
    else:
        _recover_abstracts(all_records)

    # Snapshot per-db records *before* dedup mutates them in place (exact-DOI
    # field merging and post-ASySD sibling fill both mutate Record objects
    # that are shared with all_records_by_db). Without this, the "raw"
    # per-database audit CSVs would silently pick up cross-database title/
    # abstract merges from records that happened to become a merge "keeper",
    # making them unreliable as a record of what each database actually
    # returned.
    all_records_by_db_snapshot = copy.deepcopy(all_records_by_db)

    # Deduplication
    deduped, dedup_stats = _run_deduplication(all_records, search_dir)

    # Export
    export_results(
        deduped, all_records_by_db_snapshot, queries, per_db, dedup_stats,
        output_dir=search_dir,
        search_mode=search_mode,
        search_start_year=search_start_year,
        search_end_date=search_end_date,
    )

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


# ---------------------------------------------------------------------------
# MAIN DISPATCHER
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging(OUTPUT_DIR)

    if DEDUP_ONLY_DIR:
        # --dedup <dir>: load + dedup + export only
        run_dedup(OUTPUT_DIR)
        return

    # --search mode (default or --no-dedup)
    all_records, all_records_by_db, per_db, queries = run_searches()

    if NO_DEDUP:
        # Search-only mode: save raw CSVs, print instructions, stop
        log.info("--no-dedup: skipping deduplication. Saving raw per-database CSVs.")
        for db_name, db_records in all_records_by_db.items():
            raw_path = OUTPUT_DIR / f"raw_{db_name}.csv"
            _write_csv(db_records, raw_path)
            log.info(f"Wrote {len(db_records)} raw records from {db_name} -> {raw_path}")

        log.info("=" * 60)
        log.info("Search phase complete. Manual exports needed:")
        log.info("  1. EBSCOhost PsycInfo: copy query from queries.txt -> "
                 "run on EBSCOhost -> export as CSV -> drop file(s) into:")
        log.info(f"     {OUTPUT_DIR.resolve()}")
        log.info("  2. (If WoS API was unavailable) WoS: copy query from queries.txt -> "
                 "run on Web of Science -> export as RIS -> drop file into:")
        log.info(f"     {OUTPUT_DIR.resolve()}")
        log.info("")
        log.info("Once all manual exports are added, run:")
        log.info(f"  python fnd_meta_search.py --dedup {OUTPUT_DIR}")
        log.info("=" * 60)
        return

    # Default mode: search + dedup + export in one pass.
    # Snapshot per-db records before dedup mutates them in place (see the
    # matching comment in run_dedup()) so the raw per-database audit CSVs
    # stay faithful to what each database actually returned.
    all_records_by_db_snapshot = copy.deepcopy(all_records_by_db)
    deduped, dedup_stats = _run_deduplication(all_records, OUTPUT_DIR)

    # Fetch abstracts for deduplicated Scopus-sourced records still missing them.
    # This covers the post-dedup path for simple dedup where we didn't pre-enrich.
    scopus_need_abstract = [r for r in deduped
                            if r.source_db == "scopus" and not r.abstract]
    if scopus_need_abstract:
        log.info(f"Fetching abstracts for {len(scopus_need_abstract)} Scopus-only "
                 f"records (post-dedup)")
        ScopusClient()._enrich_abstracts(scopus_need_abstract)

    export_results(
        deduped, all_records_by_db_snapshot, queries, per_db, dedup_stats,
        output_dir=OUTPUT_DIR,
        search_mode=SEARCH_MODE,
        search_start_year=SEARCH_START_YEAR,
        search_end_date=SEARCH_END_DATE,
    )

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
