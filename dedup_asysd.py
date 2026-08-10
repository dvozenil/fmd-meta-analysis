"""
ASySD-class deduplication algorithm — Python port
==================================================

Ports the Automated Systematic Search Deduplicator (ASySD) from R to Python.
Faithfully reproduces the matching rules from the original R source
(internal.R: identify_true_matches, match_citations, format_citations,
generate_dup_id).

Key differences from the R original:
  - Uses rapidfuzz.distance.JaroWinkler instead of RecordLinkage::jarowinkler
  - Uses networkx connected components instead of igraph
  - Operates on plain dicts instead of R dataframes
  - Fields pages, volume, number, isbn default to None (not in current Record)
  - Keeps one record per duplicate group (no citation merging) — the R
    merge_metadata function is not ported because the Record dataclass
    doesn't carry those extra fields.

The public API is ``deduplicate_asysd()`` which accepts a list of dicts
and returns (unique_records, stats, maybe_pairs).
"""

from __future__ import annotations

import csv
import logging
import re
import string
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from rapidfuzz.distance import JaroWinkler

log = logging.getLogger(__name__)

# ── Punctuation pattern matching R's [[:punct:]] ──────────────────────────
# R's [:punct:] matches: ! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~
_PUNCT_RE = re.compile(r"[" + re.escape(string.punctuation) + r"]")


# ════════════════════════════════════════════════════════════════════════════
# JARO-WINKLER SIMILARITY
# ════════════════════════════════════════════════════════════════════════════

def _jw(a: str | None, b: str | None) -> float:
    """Jaro-Winkler normalized similarity (0.0–1.0).

    Returns 0.0 for None/empty inputs.  Callers handle the special
    both-missing cases (pages, volume, number → 1.0) separately.
    """
    if a is None or b is None:
        return 0.0
    a_s = str(a)
    b_s = str(b)
    if not a_s or not b_s:
        return 0.0
    return JaroWinkler.normalized_similarity(a_s, b_s)


# ════════════════════════════════════════════════════════════════════════════
# ERRATUM / CORRECTION DETECTION
# ════════════════════════════════════════════════════════════════════════════

# Match erratum/correction markers anywhere in the title (word-boundary),
# not just as a prefix.  This catches titles like:
#   "Erratum: Uncovering the etiology..."     (prefix — common in WoS/Scopus)
#   "...functional neuroimaging" Corrigendum   (suffix — common in PsycINFO)
_ERRATUM_TITLE_RE = re.compile(
    r"\b(?:erratum|errata|correction|corrigendum|corrigenda|"
    r"retract|retracted|retraction|retractions|withdrawal)\b",
    re.IGNORECASE,
)


def _is_erratum_title(title: str | None) -> bool:
    """True if a title marks a correction/erratum/retraction record.

    Used to demote exact-DOI pairs where exactly one side is an erratum:
    those pairs share a DOI but represent distinct publications (the
    original article and the notice about it), and silently merging
    them drops the original article behind an erratum stub during
    screening.
    """
    if title is None:
        return False
    return bool(_ERRATUM_TITLE_RE.search(str(title)))


# ════════════════════════════════════════════════════════════════════════════
# FORMATTING / NORMALIZATION  (port of format_citations + order_citations)
# ════════════════════════════════════════════════════════════════════════════

def _normalize_author(author: str | None) -> str | None:
    """Port of format_citations author normalization.

    R's format_citations replaces "", NA, "Anonymous", "Anonymous." with
    "Unknown" (which becomes "UNKNOWN" after uppercasing).  This is critical:
    when one database (e.g. Scopus) has empty authors, the R code matches
    "UNKNOWN" vs "UNKNOWN" = 1.0, letting other fields drive the match.
    If we return None here, JW returns 0.0, blocking all author-dependent
    rules.
    """
    if author is None:
        return "UNKNOWN"
    a = str(author).strip()
    if a == "" or a == "NA":
        return "UNKNOWN"
    if a in ("Anonymous", "Anonymous.", "[Anonymous] A"):
        return "UNKNOWN"
    return a.upper()


def _clean_doi(doi: str | None) -> str | None:
    """Port of format_citations DOI cleaning, plus basic validity check.

    Rejects values that do not look like DOIs after cleaning (e.g. bare
    ``232``), so they cannot create false exact-DOI matches.
    """
    if doi is None or str(doi).strip() == "" or str(doi).strip() == "NA":
        return None
    d = str(doi).upper()
    d = d.replace("%28", "(")
    d = d.replace("%29", ")")
    for prefix in ("HTTP://DX.DOI.ORG/", "HTTPS://DOI.ORG/",
                    "HTTPS://DX.DOI.ORG/", "HTTP://DOI.ORG/"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.replace("DOI: ", "").replace("DOI:", "").replace("DOI", "")
    d = d.strip()
    if d == "" or not d.startswith("10."):
        return None
    return d


def _remove_punct(s: str | None) -> str | None:
    """Remove all punctuation (R's [[:punct:]])."""
    if s is None or str(s).strip() == "" or str(s).strip() == "NA":
        return None
    return _PUNCT_RE.sub("", str(s))


def _clean_pages(pages: Any) -> str | None:
    """Normalize page formatting: -- → -."""
    if pages is None:
        return None
    p = str(pages).strip()
    if p == "" or p == "NA":
        return None
    p = p.replace("--", "-")
    return p.upper()


def _clean_isbn(isbn: Any) -> str | None:
    """Port of format_citations ISBN cleaning."""
    if isbn is None:
        return None
    s = str(isbn).strip()
    if s == "" or s == "NA":
        return None
    s = re.sub(r"\s*\(PRINT\).*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*\(ELECTRONIC\).*", "", s, flags=re.IGNORECASE)
    return s.upper()


def _upper_or_none(v: Any) -> str | None:
    """Uppercase a value or return None for blank/NA."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s == "NA":
        return None
    return s.upper()


def _to_str_or_none(v: Any) -> str | None:
    """Convert to string, return None for blank/NA."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s == "NA":
        return None
    return s


def format_citations(records: list[dict]) -> list[dict]:
    """Port of R's format_citations() — normalizes all fields for matching.

    Returns a new list of dicts with keys:
        author, title, year, journal, abstract, doi, number, pages, volume,
        isbn, record_id, source, label
    """
    formatted = []
    for rec in records:
        # Author: join list if needed, then normalize
        author_raw = rec.get("author")
        if isinstance(author_raw, list):
            author_raw = "; ".join(str(a) for a in author_raw if a)

        author = _normalize_author(author_raw)
        title = _remove_punct(_upper_or_none(rec.get("title")))
        year = _to_str_or_none(rec.get("year"))
        if year is not None:
            year = _remove_punct(year)
        journal = _upper_or_none(rec.get("journal"))
        abstract = _remove_punct(_upper_or_none(rec.get("abstract")))
        doi = _clean_doi(rec.get("doi"))
        number = _to_str_or_none(rec.get("number"))
        pages = _clean_pages(rec.get("pages"))
        volume = _to_str_or_none(rec.get("volume"))
        isbn = _clean_isbn(rec.get("isbn"))
        record_id = str(rec.get("record_id", "")).strip()
        source = _to_str_or_none(rec.get("source")) or "unknown"
        label = _to_str_or_none(rec.get("label")) or "unknown"

        formatted.append({
            "author": author,
            "title": title,
            "year": year,
            "journal": journal,
            "abstract": abstract,
            "doi": doi,
            "number": number,
            "pages": pages,
            "volume": volume,
            "isbn": isbn,
            "record_id": record_id,
            "source": source,
            "label": label,
        })
    return formatted


def order_citations(records: list[dict],
                    keep_source: str | None = None) -> list[dict]:
    """Order records so the *first* row in each duplicate group is preferred.

    ASySD's R code sorts ascending and keeps ``slice_head()`` (first).  The
    original port treated empty abstracts as preferred, which systematically
    discarded complete records.  We instead prefer:

      1. non-empty abstract
      2. ``keep_source`` (e.g. pubmed) when set
      3. longer abstract / longer title (completeness)
      4. newer year
    """
    def sort_key(r: dict) -> tuple:
        abstract = str(r.get("abstract") or "").strip()
        title = str(r.get("title") or "").strip()
        year_s = str(r.get("year") or "").strip()
        try:
            year_n = int(year_s) if year_s else 0
        except ValueError:
            year_n = 0
        source = r.get("source") or ""
        return (
            0 if abstract else 1,                          # has abstract first
            0 if (keep_source and source == keep_source) else 1,
            -len(abstract),
            -len(title),
            -year_n,
            str(r.get("record_id") or ""),
        )

    return sorted(records, key=sort_key)


# ════════════════════════════════════════════════════════════════════════════
# BLOCKING + PAIR GENERATION  (port of match_citations)
# ════════════════════════════════════════════════════════════════════════════

# Field indices in formatted citations (1-based in R, we use names):
#  1=author  2=title  3=year  4=journal  5=abstract
#  6=doi     7=number 8=pages 9=volume  10=isbn
#  11=record_id  12=source  13=label

# Blocking strategies from match_citations — each tuple is a set of fields
# that must match exactly (same value, case-insensitive) for a pair to be
# considered.  R's compare.dedup blocks on exact equality.
_BLOCKING_ROUNDS = [
    # Round 1: title&pages, title&author, title&abstract, doi
    [("title", "pages"), ("title", "author"), ("title", "abstract"), ("doi",)],
    # Round 2: author&year&pages, journal&volume&pages, isbn&volume&pages, title&isbn
    [("author", "year", "pages"), ("journal", "volume", "pages"),
     ("isbn", "volume", "pages"), ("title", "isbn")],
    # Round 3: year&pages&volume, year&number&volume, year&pages&number
    [("year", "pages", "volume"), ("year", "number", "volume"),
     ("year", "pages", "number")],
    # Round 4: author&year, year&title, title&volume, title&journal
    [("author", "year"), ("year", "title"), ("title", "volume"), ("title", "journal")],
]


def _block_key(rec: dict, fields: tuple[str, ...]) -> str:
    """Create an exact-match block key for the given fields."""
    parts = []
    for f in fields:
        v = rec.get(f)
        parts.append(str(v).lower() if v is not None else "\x00NULL")
    return "|".join(parts)


def _generate_candidate_pairs(formatted: list[dict]) -> list[tuple[int, int]]:
    """Generate candidate pairs using blocking strategies.

    Port of match_citations blocking logic. Returns list of (i, j) index
    pairs where i < j.
    """
    candidate_pairs: set[tuple[int, int]] = set()

    for round_blocks in _BLOCKING_ROUNDS:
        for block_fields in round_blocks:
            # Group records by block key
            blocks: dict[str, list[int]] = {}
            for idx, rec in enumerate(formatted):
                # Skip records where ALL block fields are None/empty
                values = [rec.get(f) for f in block_fields]
                if all(v is None or str(v).strip() == "" for v in values):
                    continue
                key = _block_key(rec, block_fields)
                blocks.setdefault(key, []).append(idx)

            # Generate pairs within each block
            for indices in blocks.values():
                if len(indices) < 2:
                    continue
                for i_pos in range(len(indices)):
                    for j_pos in range(i_pos + 1, len(indices)):
                        i, j = indices[i_pos], indices[j_pos]
                        if i > j:
                            i, j = j, i
                        candidate_pairs.add((i, j))

    return sorted(candidate_pairs)


@dataclass
class PairData:
    """Similarity scores for a candidate pair."""
    id1: int
    id2: int
    author: float
    title: float
    abstract: float
    year: float
    pages: float
    number: float
    volume: float
    journal: float
    isbn: float
    doi: float
    # Raw values for post-filtering (year mismatch, DOI mismatch)
    year1: str | None
    year2: str | None
    doi1: str | None
    doi2: str | None
    record_id1: str
    record_id2: str
    title1: str | None
    title2: str | None
    author1: str | None
    author2: str | None
    journal1: str | None
    journal2: str | None


def _compute_pair_similarities(formatted: list[dict],
                               pairs: list[tuple[int, int]]) -> list[PairData]:
    """Compute Jaro-Winkler similarities for all candidate pairs.

    Port of the similarity computation + NA handling in match_citations.
    """
    result = []
    for i, j in pairs:
        r1 = formatted[i]
        r2 = formatted[j]

        # Compute raw JW similarities
        author_sim = _jw(r1.get("author"), r2.get("author"))
        title_sim = _jw(r1.get("title"), r2.get("title"))
        abstract_sim = _jw(r1.get("abstract"), r2.get("abstract"))
        year_sim = _jw(r1.get("year"), r2.get("year"))
        pages_sim = _jw(r1.get("pages"), r2.get("pages"))
        number_sim = _jw(r1.get("number"), r2.get("number"))
        volume_sim = _jw(r1.get("volume"), r2.get("volume"))
        journal_sim = _jw(r1.get("journal"), r2.get("journal"))
        isbn_sim = _jw(r1.get("isbn"), r2.get("isbn"))
        doi_sim = _jw(r1.get("doi"), r2.get("doi"))

        # NA/missing handling (port from match_citations lines 310-318)
        # abstract: both NA → 0
        if r1.get("abstract") is None and r2.get("abstract") is None:
            abstract_sim = 0.0
        # pages: both NA → 1
        if r1.get("pages") is None and r2.get("pages") is None:
            pages_sim = 1.0
        # volume: both NA → 1
        if r1.get("volume") is None and r2.get("volume") is None:
            volume_sim = 1.0
        # number: both NA → 1
        if r1.get("number") is None and r2.get("number") is None:
            number_sim = 1.0
        # doi: both NA → 0
        if r1.get("doi") is None and r2.get("doi") is None:
            doi_sim = 0.0
        # isbn: both NA → 0
        if r1.get("isbn") is None and r2.get("isbn") is None:
            isbn_sim = 0.0
        # year: both NA → 0
        if r1.get("year") is None and r2.get("year") is None:
            year_sim = 0.0
        # journal: both NA → 0
        if r1.get("journal") is None and r2.get("journal") is None:
            journal_sim = 0.0

        result.append(PairData(
            id1=i, id2=j,
            author=author_sim, title=title_sim, abstract=abstract_sim,
            year=year_sim, pages=pages_sim, number=number_sim,
            volume=volume_sim, journal=journal_sim, isbn=isbn_sim,
            doi=doi_sim,
            year1=r1.get("year"), year2=r2.get("year"),
            doi1=r1.get("doi"), doi2=r2.get("doi"),
            record_id1=r1.get("record_id", str(i)),
            record_id2=r2.get("record_id", str(j)),
            title1=r1.get("title"), title2=r2.get("title"),
            author1=r1.get("author"), author2=r2.get("author"),
            journal1=r1.get("journal"), journal2=r2.get("journal"),
        ))
    return result


# ════════════════════════════════════════════════════════════════════════════
# IDENTIFY TRUE MATCHES  (port of identify_true_matches)
# ════════════════════════════════════════════════════════════════════════════

def _is_true_match(p: PairData) -> bool:
    """Apply the ~25 OR-combined threshold rules from identify_true_matches.

    Each rule is a conjunction of field > threshold.  If any rule passes,
    the pair is a true match (subject to post-filtering).
    """
    a, t, ab = p.author, p.title, p.abstract
    pg, nm, vol, jnl, isbn, doi = p.pages, p.number, p.volume, p.journal, p.isbn, p.doi

    rules = [
        # Lines 333-364 in internal.R — all OR-combined
        (pg > 0.8 and vol > 0.8 and t > 0.90 and ab > 0.90 and a > 0.50 and isbn > 0.99),
        (pg > 0.8 and vol > 0.8 and t > 0.90 and ab > 0.90 and a > 0.50 and jnl > 0.6),
        (pg > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.90 and a > 0.50 and jnl > 0.6),
        (vol > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.90 and a > 0.50 and jnl > 0.6),

        (vol > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.90 and a > 0.8),
        (vol > 0.8 and pg > 0.8 and t > 0.90 and ab > 0.9 and a > 0.8),
        (pg > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.9 and a > 0.8),

        (doi > 0.95 and a > 0.75 and t > 0.9),

        # Exact cleaned-DOI match is decisive on its own.  Title/author can
        # be truncated or formatted differently across databases; requiring
        # them blocked true cross-DB duplicates (see maybe_pairs same-DOI).
        # Gross title conflicts are demoted to maybe_pairs in
        # identify_true_matches.
        doi >= 1.0,

        (t > 0.80 and ab > 0.90 and vol > 0.85 and jnl > 0.65 and a > 0.9),
        (t > 0.90 and ab > 0.80 and vol > 0.85 and jnl > 0.65 and a > 0.9),

        (pg > 0.8 and vol > 0.8 and t > 0.90 and ab > 0.8 and a > 0.9 and jnl > 0.75),
        (pg > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.80 and a > 0.9 and jnl > 0.75),
        (vol > 0.8 and nm > 0.8 and t > 0.90 and ab > 0.8 and a > 0.9 and jnl > 0.75),

        (t > 0.9 and a > 0.9 and ab > 0.9 and jnl > 0.7),
        (t > 0.9 and a > 0.9 and ab > 0.9 and isbn > 0.99),

        (pg > 0.9 and nm > 0.9 and t > 0.90 and a > 0.80 and jnl > 0.6),
        (nm > 0.9 and vol > 0.9 and t > 0.90 and a > 0.90 and isbn > 0.99),
        (pg > 0.9 and vol > 0.9 and t > 0.90 and a > 0.80 and jnl > 0.6),
        (pg > 0.9 and nm > 0.9 and t > 0.90 and a > 0.80 and isbn > 0.99),

        (pg > 0.8 and vol > 0.8 and t > 0.95 and a > 0.80 and jnl > 0.9),
        (nm > 0.8 and vol > 0.8 and t > 0.95 and a > 0.80 and jnl > 0.9),
        (nm > 0.8 and pg > 0.8 and t > 0.95 and a > 0.80 and jnl > 0.9),
        (pg > 0.8 and vol > 0.8 and t > 0.95 and a > 0.80 and isbn > 0.99),
        # Lines 363-364 are duplicates of 362 in the R source
        (pg > 0.8 and vol > 0.8 and t > 0.95 and a > 0.80 and isbn > 0.99),
        (pg > 0.8 and vol > 0.8 and t > 0.95 and a > 0.80 and isbn > 0.99),

        # ── Extension: one-side-missing-author rule ──────────────────────
        # ASySD assumes all databases provide authors.  When one database
        # (e.g. Scopus in our pipeline) has empty authors → "UNKNOWN",
        # JW("UNKNOWN", real_author) is low, blocking all author-dependent
        # rules.  This rule auto-merges when DOI + title are near-perfect
        # and one side has UNKNOWN author, treating the author mismatch as
        # a data gap rather than evidence of different papers.
        (doi > 0.95 and t > 0.95 and
         (p.author1 == "UNKNOWN" or p.author2 == "UNKNOWN")),
        # Same idea but without DOI (both missing DOI, same title, one
        # side missing authors, same year ± 1).
        (t > 0.95 and doi == 0.0 and
         (p.author1 == "UNKNOWN" or p.author2 == "UNKNOWN") and
         abs((_safe_int(p.year1) or 0) - (_safe_int(p.year2) or 0)) <= 1),
    ]
    return any(rules)


def identify_true_matches(
    pairs: list[PairData],
    protected_ids: set[str] | None = None,
) -> tuple[list[PairData], list[PairData]]:
    """Port of R's identify_true_matches().

    Parameters
    ----------
    protected_ids : set[str] | None
        Record ids that an upstream stage has already flagged as belonging
        to a gross DOI/title conflict (e.g. the exact-DOI collapse in
        ``fnd_meta_search.py``, which uses a different similarity metric
        than the in-ASySD Jaro-Winkler check below). Any pair touching a
        protected id is always demoted to ``maybe_pairs`` regardless of
        which rule matched it as "true" — this prevents ASySD from
        silently re-merging records that were quarantined for manual
        review upstream.

    Returns (true_pairs, maybe_pairs) where:
      - true_pairs are confident duplicates (after all filters)
      - maybe_pairs need manual review
    """
    protected_ids = protected_ids or set()

    # Step 1: Apply threshold rules
    true_pairs = [p for p in pairs if _is_true_match(p)]

    # Step 1b: Exact-DOI pairs with grossly conflicting titles → maybe, not true.
    # Protects against rare DOI metadata errors while still auto-merging the
    # common case (same paper, truncated/HTML-differing titles).
    #
    # Erratum-titled exact matches are also demoted, but for a different
    # reason: an erratum/correction/retraction is a *distinct publication*
    # sharing the DOI with the original article.  Merging them hides the
    # original behind the erratum stub at screening time.  Route them to
    # maybe(pairs) so a human can decide pair-by-pair.
    doi_title_conflicts: list[PairData] = []
    kept_true: list[PairData] = []
    for p in true_pairs:
        if p.doi >= 1.0:
            t1_err = _is_erratum_title(p.title1)
            t2_err = _is_erratum_title(p.title2)
            if t1_err != t2_err:
                # Exactly one side is erratum — demote regardless of title
                # similarity, because they are distinct publications.
                doi_title_conflicts.append(p)
                continue
        if (p.doi >= 1.0 and p.title1 and p.title2 and p.title < 0.6
                and len(p.title1) >= 15 and len(p.title2) >= 15):
            doi_title_conflicts.append(p)
        elif p.record_id1 in protected_ids or p.record_id2 in protected_ids:
            doi_title_conflicts.append(p)
        else:
            kept_true.append(p)
    true_pairs = kept_true

    # Step 2: DOI mismatch filter (lines 368-374)
    # Find true_pairs with low matching DOIs (not NA, not 0, not >0.99)
    true_pairs_mismatch_doi = [
        p for p in true_pairs
        if p.doi != 0.0 and p.doi > 0.0 and p.doi <= 0.99
        and not (p.title > 0.9 and p.abstract > 0.9 and
                 (p.journal > 0.9 or p.isbn > 0.9))
    ]

    # Remove DOI-mismatched pairs unless title&abstract&(journal|isbn) are very high
    true_pairs = [
        p for p in true_pairs
        if p.doi == 0.0 or p.doi > 0.99 or
           (p.title > 0.9 and p.abstract > 0.9 and (p.journal > 0.9 or p.isbn > 0.9))
    ]

    # Step 3: Year mismatch filter (lines 378-393)
    year_mismatch_major = []
    for p in true_pairs:
        y1 = _safe_int(p.year1)
        y2 = _safe_int(p.year2)
        if y1 is not None and y2 is not None and abs(y1 - y2) > 1:
            year_mismatch_major.append(p)

    if year_mismatch_major:
        major_ids = {(p.record_id1, p.record_id2) for p in year_mismatch_major}
        true_pairs = [
            p for p in true_pairs
            if (p.record_id1, p.record_id2) not in major_ids
        ]

    # Step 4: Maybe pairs (lines 396-416)
    maybe_pairs = []
    true_pair_ids = {(p.record_id1, p.record_id2) for p in true_pairs}

    for p in pairs:
        # Candidate maybe pairs
        is_maybe = (
            (p.title > 0.85 and p.author > 0.75) or
            (p.title > 0.80 and p.abstract > 0.80) or
            (p.title > 0.80 and p.isbn > 0.99) or
            (p.title > 0.80 and p.journal > 0.80)
        )
        if not is_maybe:
            continue
        # DOI filter: keep only if doi > 0.99 or doi == 0 or NA
        if p.doi > 0.0 and p.doi <= 0.99:
            continue
        # Year filter: exclude if year differs by > 1
        y1 = _safe_int(p.year1)
        y2 = _safe_int(p.year2)
        if y1 is not None and y2 is not None and abs(y1 - y2) > 1:
            continue
        # Exclude if already in true_pairs
        if (p.record_id1, p.record_id2) in true_pair_ids:
            continue
        maybe_pairs.append(p)

    # Step 5: Add important mismatches to maybe_pairs (line 414)
    for p in true_pairs_mismatch_doi:
        if (p.record_id1, p.record_id2) not in {(m.record_id1, m.record_id2) for m in maybe_pairs}:
            maybe_pairs.append(p)
    for p in year_mismatch_major:
        if (p.record_id1, p.record_id2) not in {(m.record_id1, m.record_id2) for m in maybe_pairs}:
            maybe_pairs.append(p)
    for p in doi_title_conflicts:
        if (p.record_id1, p.record_id2) not in {(m.record_id1, m.record_id2) for m in maybe_pairs}:
            maybe_pairs.append(p)

    return true_pairs, maybe_pairs


def _safe_int(v: str | None) -> int | None:
    """Safely convert a string to int."""
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


# ════════════════════════════════════════════════════════════════════════════
# DUPLICATE ID GENERATION  (port of generate_dup_id)
# ════════════════════════════════════════════════════════════════════════════

def generate_dup_id(true_pairs: list[PairData],
                    formatted: list[dict],
                    keep_source: str | None = None) -> list[dict]:
    """Port of R's generate_dup_id() — assign duplicate group IDs using
    connected components (igraph → networkx).

    Returns the formatted citations list augmented with 'duplicate_id' field.
    Records not in any duplicate pair get their own unique duplicate_id.
    """
    # Build graph from true pairs
    g = nx.Graph()
    for p in true_pairs:
        g.add_edge(p.record_id1, p.record_id2)

    # Get connected components
    components = list(nx.connected_components(g))

    # ── Defensive erratum logging ───────────────────────────────────────
    # If a component contains BOTH erratum-titled and non-erratum-titled
    # records, log it for audit.  This should be rare after Layer A
    # (pairwise demotion in identify_true_matches), but can still occur
    # via transitive closure through non-DOI rules.  We do NOT split
    # the component here — Layer A handles the pairwise case, and
    # production's _collapse_exact_dois handles same-DOI erratum groups.
    rid_to_record_for_log: dict[str, dict] = {}
    for rec in formatted:
        rid = rec["record_id"]
        rid_to_record_for_log[rid] = rec

    for members in components:
        member_list = list(members)
        erratum_members = {m for m in member_list
                           if _is_erratum_title(
                               rid_to_record_for_log.get(m, {}).get("title"))}
        original_members = set(member_list) - erratum_members
        if erratum_members and original_members:
            log.warning(
                "erratum-containing component: %d originals, %d errata "
                "(records: originals=%s, errata=%s)",
                len(original_members), len(erratum_members),
                sorted(original_members)[:5],
                sorted(erratum_members)[:5],
            )

    # Map record_id → component_id (1-based)
    record_to_component: dict[str, int] = {}
    for comp_id, members in enumerate(components, start=1):
        for rid in members:
            record_to_component[rid] = comp_id

    # Assign duplicate_id: for each component, pick the "best" record_id
    # to be the duplicate_id.  If keep_source is set, prefer records from
    # that source.  Otherwise, use the first record_id alphabetically
    # (R uses arrange(record_id) when no keep_source/keep_label).

    # Build a lookup of record_id → source from formatted
    rid_to_source: dict[str, str] = {}
    rid_to_record: dict[str, dict] = {}
    for rec in formatted:
        rid = rec["record_id"]
        rid_to_source[rid] = rec.get("source", "unknown")
        rid_to_record[rid] = rec

    component_to_dup_id: dict[int, str] = {}
    for comp_id, members in enumerate(components, start=1):
        member_list = list(members)
        if keep_source:
            # Prefer records from keep_source
            preferred = [m for m in member_list if rid_to_source.get(m) == keep_source]
            chosen = sorted(preferred)[0] if preferred else sorted(member_list)[0]
        else:
            # R: arrange(record_id) then first()
            chosen = sorted(member_list)[0]
        component_to_dup_id[comp_id] = chosen

    # Assign duplicate_id to all records
    next_id = len(components) + 1
    for rec in formatted:
        rid = rec["record_id"]
        if rid in record_to_component:
            comp_id = record_to_component[rid]
            rec["duplicate_id"] = component_to_dup_id[comp_id]
        else:
            # Not in any duplicate pair — own unique id
            rec["duplicate_id"] = rid
            next_id += 1

    return formatted


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════════

def deduplicate_asysd(
    records: list[dict],
    keep_source: str | None = None,
    protected_ids: set[str] | None = None,
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """ASySD-class deduplication.

    Parameters
    ----------
    records : list[dict]
        List of citation dicts with keys: source, record_id, author, title,
        year, journal, abstract, doi, number, pages, volume, isbn, label.
        Fields not present in the Record dataclass (pages, volume, number,
        isbn) default to None.
    keep_source : str | None
        If set, preferentially keep records from this source as the
        representative in each duplicate group.
    protected_ids : set[str] | None
        Record ids quarantined by an upstream conflict check (see
        ``identify_true_matches``). Pairs touching these ids are never
        auto-merged as "true" duplicates; they are demoted to
        ``maybe_pairs`` for manual review instead.

    Returns
    -------
    (unique_records, stats, maybe_pairs)
        unique_records : list[dict] — one record per duplicate group
        stats          : dict with keys total_raw, unique, duplicates_removed
        maybe_pairs    : list[dict] — pairs flagged for manual review
    """
    if not records:
        return [], {"total_raw": 0, "unique": 0, "duplicates_removed": 0}, []

    # Step 1: Order and format citations
    log.info(f"ASySD: formatting {len(records)} records...")
    ordered = order_citations(records, keep_source=keep_source)
    formatted = format_citations(ordered)

    # Step 2: Generate candidate pairs via blocking
    log.info("ASySD: generating candidate pairs via blocking...")
    candidate_pairs = _generate_candidate_pairs(formatted)
    log.info(f"ASySD: {len(candidate_pairs)} candidate pairs generated")

    if not candidate_pairs:
        # No duplicates possible
        for rec in formatted:
            rec["duplicate_id"] = rec["record_id"]
        stats = {
            "total_raw": len(records),
            "unique": len(records),
            "duplicates_removed": 0,
        }
        return formatted, stats, []

    # Step 3: Compute similarities
    log.info("ASySD: computing Jaro-Winkler similarities...")
    pair_data = _compute_pair_similarities(formatted, candidate_pairs)

    # Step 4: Identify true and maybe matches
    log.info("ASySD: identifying true matches...")
    true_pairs, maybe_pairs = identify_true_matches(pair_data, protected_ids=protected_ids)
    log.info(f"ASySD: {len(true_pairs)} true duplicate pairs, "
             f"{len(maybe_pairs)} maybe pairs for manual review")

    # Step 5: Generate duplicate IDs
    log.info("ASySD: generating duplicate IDs via connected components...")
    formatted = generate_dup_id(true_pairs, formatted, keep_source)

    # Step 6: Keep one record per duplicate group
    # R's keep_one_unique_citation: group_by(duplicate_id) %>% slice_head()
    seen_dup_ids: set[str] = set()
    unique_records: list[dict] = []
    for rec in formatted:
        dup_id = rec["duplicate_id"]
        if dup_id not in seen_dup_ids:
            seen_dup_ids.add(dup_id)
            unique_records.append(rec)

    stats = {
        "total_raw": len(records),
        "unique": len(unique_records),
        "duplicates_removed": len(records) - len(unique_records),
    }

    # Convert maybe_pairs to dicts for output
    maybe_pairs_out = [
        {
            "record_id1": p.record_id1,
            "record_id2": p.record_id2,
            "title1": p.title1,
            "title2": p.title2,
            "author1": p.author1,
            "author2": p.author2,
            "year1": p.year1,
            "year2": p.year2,
            "doi1": p.doi1,
            "doi2": p.doi2,
            "title_sim": round(p.title, 4),
            "author_sim": round(p.author, 4),
            "abstract_sim": round(p.abstract, 4),
            "doi_sim": round(p.doi, 4),
            "journal_sim": round(p.journal, 4),
            "conflict_type": (
                "doi_erratum" if (
                    p.doi >= 1.0
                    and _is_erratum_title(p.title1) != _is_erratum_title(p.title2)
                ) else ""
            ),
        }
        for p in maybe_pairs
    ]

    log.info(f"ASySD: {stats['unique']} unique records, "
             f"{stats['duplicates_removed']} duplicates removed")

    return unique_records, stats, maybe_pairs_out
