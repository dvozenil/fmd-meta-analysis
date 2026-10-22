"""Unit tests for the WoS RIS multi-DOI fix and the post-dedup same-title sweep.

Covers two dedup-quality fixes:

1. ``_pick_first_doi`` (fnd_meta_search._import_ris): WoS RIS exports can
   concatenate MULTIPLE DOIs into one space-separated DO field — production
   example from the 2026-07-31 corpus:
   ``10.1159/000360062 10.1159/isbn.978-3-318`` (article DOI + book ISBN DOI).
   The importer must keep the first genuine article DOI and skip ISBN-style
   tokens; single-token fields must pass through byte-identically (golden
   behavior — existing pipeline outputs must not change).

2. ``scripts/same_title_sweep.py``: post-dedup sweep that flags residual
   same-title duplicate candidates into a maybe-pairs CSV. The production
   validation case is the frozen corpus
   ``data/screening_corpus_2026-07-31/records_deduplicated_adjudicated.csv``
   (if present), which is known to contain 13 leaked true-duplicate pairs.
   The sweep must catch them WITHOUT flagging the generic-title
   "Conversion disorder." groups (distinct works with empty DOIs — the
   empty==empty over-merge was the original exploratory-pass bug).
"""

import csv
import sys
import tempfile
from pathlib import Path

# Allow running from repo root without installation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fnd_meta_search import _import_ris, _normalize_doi, _pick_first_doi

# Import the sweep module (plain import, not via package machinery)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import same_title_sweep as sts  # noqa: E402


# ---------------------------------------------------------------------------
# Part 1: _pick_first_doi — WoS multi-DOI field splitting
# ---------------------------------------------------------------------------

# The two production Hysteria records (2026-07-31 corpus, WOS export):
#   WOS:000387704900018  '10.1159/000360062 10.1159/isbn.978-3-318-02647-4'
#   WOS:000387704900020  '10.1159/000360064 10.1159/isbn.978-3-318-02647-4'
HYSTERIA_RIS = """TY  - CHAP
AN  - WOS:000387704900018
TI  - Hysteria around the World
DO  - 10.1159/000360062 10.1159/isbn.978-3-318-02647-4
PY  - 2016
AU  - Bogousslavsky, J.
ER  -

TY  - CHAP
AN  - WOS:000387704900020
TI  - 'Hysteria' Today and Tomorrow
DO  - 10.1159/000360064 10.1159/isbn.978-3-318-02647-4
PY  - 2016
AU  - Bogousslavsky, J.
ER  -
"""


def _ris_records(tmp_path, text):
    p = tmp_path / "test.ris"
    p.write_text(text, encoding="utf-8")
    return _import_ris(p, "wos")


def test_pick_first_doi_wos_hysteria_multi_doi():
    """The production leak: article DOI + ISBN DOI space-joined in one field."""
    assert _pick_first_doi("10.1159/000360062 10.1159/isbn.978-3-318") == "10.1159/000360062"
    assert _pick_first_doi("10.1159/000360064 10.1159/isbn.978-3-318") == "10.1159/000360064"
    # Full-length production form.
    assert _pick_first_doi(
        "10.1159/000360062 10.1159/isbn.978-3-318-02647-4"
    ) == "10.1159/000360062"


def test_pick_first_doi_single_token_passes_through_byte_identically():
    """Golden-pinned behavior: single-token fields must NOT be split/normalized."""
    for s in ("10.1159/000360062", "10.1016/j.yebeh.2016.09.015",
              "10.1007/s00702-019-01977-2"):
        assert _pick_first_doi(s) == s, s
    # Degenerate inputs pass through unchanged.
    assert _pick_first_doi(None) is None
    assert _pick_first_doi("") is None
    # Whitespace-only: normalized to None downstream (matches pre-fix behavior,
    # where _normalize_doi("  ") also returned None).
    assert _pick_first_doi("  ") is None


def test_pick_first_doi_isbn_only_field_yields_none():
    """If ALL tokens are ISBN-style, keep none (a bare book ISBN is not an article DOI)."""
    assert _pick_first_doi("10.1159/isbn.978-3-318 10.1159/isbn.978-3-319") is None
    assert _pick_first_doi("10.1159/isbn.978-3-318") == "10.1159/isbn.978-3-318"


def test_pick_first_doi_isbn_token_before_article_doi():
    """Order-independent: skip a leading ISBN token, keep the article DOI."""
    assert _pick_first_doi(
        "10.1159/isbn.978-3-318-02647-4 10.1159/000360062"
    ) == "10.1159/000360062"


def test_pick_first_doi_two_article_dois_keeps_first():
    """Two genuine article DOIs: keep the first (conservative behavior)."""
    assert _pick_first_doi(
        "10.1016/j.yebeh.2016.09.015 10.1007/s00702-019-01977-2"
    ) == "10.1016/j.yebeh.2016.09.015"


def test_pick_first_doi_isbn_case_insensitive():
    assert _pick_first_doi("10.1159/000360062 10.1159/ISBN.978-3-318") == "10.1159/000360062"


def test_pick_first_doi_bare_isbn_single_token_untouched():
    """A single ISBN-style token passes through untouched (conservative: only
    multi-token fields are split)."""
    assert _pick_first_doi("10.1159/isbn.978-3-318") == "10.1159/isbn.978-3-318"


def test_import_ris_hysteria_records_doi():
    """End-to-end through _import_ris with a minimal RIS fixture."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        recs = _ris_records(Path(td), HYSTERIA_RIS)
    assert len(recs) == 2
    by_title = {r.title: r for r in recs}
    assert _normalize_doi(by_title["Hysteria around the World"].doi) == "10.1159/000360062"
    assert _normalize_doi(by_title["'Hysteria' Today and Tomorrow"].doi) == "10.1159/000360064"


def test_import_ris_single_doi_record_unchanged():
    """A normal single-DOI RIS record still imports byte-identically."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        recs = _ris_records(Path(td), (
            "TY  - JOUR\n"
            "TI  - Some ordinary article\n"
            "DO  - 10.1016/j.yebeh.2016.09.015\n"
            "PY  - 2016\n"
            "AU  - Smith, J.\n"
            "ER  -\n"
        ))
    assert len(recs) == 1
    assert recs[0].doi == "10.1016/j.yebeh.2016.09.015"


def test_import_ris_empty_doi_record():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        recs = _ris_records(Path(td), (
            "TY  - JOUR\n"
            "TI  - No DOI at all here\n"
            "PY  - 2016\n"
            "ER  -\n"
        ))
    assert len(recs) == 1
    assert recs[0].doi is None


def test_import_ris_wos_book_chapter_figshare_not_subsumed():
    """A figshare-style deposit DOI (single token) is NOT split or dropped."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        recs = _ris_records(Path(td), (
            "TY  - DATA\n"
            "TI  - A deposited dataset\n"
            "DO  - 10.6084/m9.figshare.1632793.v1\n"
            "PY  - 2017\n"
            "ER  -\n"
        ))
    assert recs[0].doi == "10.6084/m9.figshare.1632793.v1"


# ---------------------------------------------------------------------------
# Part 2: same_title_sweep — helpers
# ---------------------------------------------------------------------------

def _rec(source_db, source_id, title, doi="", year="", authors="", abstract=""):
    return {"source_db": source_db, "source_id": source_id, "doi": doi,
            "title": title, "abstract": abstract, "authors": authors, "year": year}


def test_normalize_title_strips_punct_case_whitespace():
    assert sts.normalize_title("  'Hysteria' Today, and Tomorrow!  ") == \
        "hysteria today and tomorrow"
    assert sts.normalize_title("Structural and Functional Brain Network Alterations") == \
        sts.normalize_title("structural and functional brain network ALTERATIONS")
    assert sts.normalize_title(None) == ""
    assert sts.normalize_title("   ") == ""


def test_author_last_names_formats():
    # wos/psycinfo 'Last, First; Last, First'
    assert sts._author_last_names("Redwine, Karen E.; Williams, P. B.") == \
        {"redwine", "williams"}
    # scopus 'Last F.M.; Last F.'
    assert sts._author_last_names("Espay A.J.; Rodriguez-Porcel F.") == \
        {"espay", "rodriguez-porcel"}
    # Accented names fold to ASCII.
    assert sts._author_last_names("Müller, Hans") == {"muller"}
    assert sts._author_last_names("") == set()
    assert sts._author_last_names(None) == set()


# ---------------------------------------------------------------------------
# Part 2: same_title_sweep — classification rules
# ---------------------------------------------------------------------------

def test_classify_same_doi_true_dup():
    r1 = _rec("scopus", "S1", "Hysteria around the world", doi="10.1159/000360062")
    r2 = _rec("wos", "W1", "Hysteria around the world", doi="10.1159/000360062")
    assert sts._classify(r1, r2, 0.0) == "TRUE_DUP_CANDIDATE"


def test_classify_missing_doi_is_unknown_never_equal():
    """THE regression case: two distinct works, same generic title, both DOIs
    empty — must NOT be flagged (the empty==empty exploratory-pass bug)."""
    r1 = _rec("psycinfo", "P1", "Conversion disorder.", doi="", year="2017",
              authors="Loriedo, Camillo; Di Leone, Flavio G.", abstract="A" * 200)
    r2 = _rec("psycinfo", "P2", "Conversion disorder.", doi="", year="2018",
              authors="Feinstein, Anthony", abstract="B" * 200)
    assert sts._classify(r1, r2, 0.0) is None
    # Even identical years: without author overlap it must not merge.
    r3 = _rec("psycinfo", "P3", "Conversion disorder.", doi="", year="2017",
              authors="Feinstein, Anthony")
    assert sts._classify(r1, r3, 0.0) is None


def test_classify_missing_doi_with_year_and_author_overlap():
    """Both DOIs absent + same year + shared author last name -> true-dup."""
    r1 = _rec("psycinfo", "P1", "Pseudoseizures, trauma", doi="", year="2011",
              authors="Redwine, Karen E.")
    r2 = _rec("wos", "W1", "Pseudoseizures, trauma", doi="", year="2011",
              authors="Redwine, K. E.; Williams, P. B.")
    assert sts._classify(r1, r2, 0.0) == "TRUE_DUP_CANDIDATE"


def test_classify_missing_doi_year_mismatch():
    r1 = _rec("psycinfo", "P1", "Same title", doi="", year="2011", authors="Redwine, K.")
    r2 = _rec("wos", "W1", "Same title", doi="", year="2012", authors="Redwine, K.")
    assert sts._classify(r1, r2, 0.0) is None


def test_classify_missing_doi_author_mismatch():
    r1 = _rec("psycinfo", "P1", "Same title", doi="", year="2011", authors="Redwine, K.")
    r2 = _rec("wos", "W1", "Same title", doi="", year="2011", authors="Smith, J.")
    assert sts._classify(r1, r2, 0.0) is None


def test_classify_abstract_similarity_threshold():
    r1 = _rec("wos", "W1", "Structural Organization", doi="", year="2016")
    r2 = _rec("wos", "W2", "Structural Organization", doi="", year="2016")
    # High abstract similarity flags even without authors (year+authors rule
    # needs both, but abstract sim alone is a true-dup signal).
    assert sts._classify(r1, r2, 0.93) == "TRUE_DUP_CANDIDATE"
    # Below threshold, no corroboration -> not flagged.
    assert sts._classify(r1, r2, 0.5) is None


def test_classify_preprint_pairs():
    pub = _rec("psycinfo", "P1", "Functional movement disorder", doi="10.3389/fpsyt.2025.1473913")
    pre = _rec("wos", "W1", "Functional movement disorder", doi="10.1101/2024.07.23.24310881")
    assert sts._classify(pub, pre, 0.0) == "PREPRINT_CANDIDATE"
    # 10.64898/ prefix also recognized.
    pre2 = _rec("wos", "W2", "Functional movement disorder", doi="10.64898/2026.01.06")
    pub2 = _rec("wos", "W3", "Functional movement disorder", doi="10.1016/j.nicl.2026.103996")
    assert sts._classify(pub2, pre2, 0.0) == "PREPRINT_CANDIDATE"
    # Both preprints (same prefix both sides) -> not classified as preprint pair.
    assert sts._classify(pre, _rec("x", "X", "t", doi="10.1101/2023.1.1.1"), 0.0) is None


def test_classify_different_dois_both_non_preprint_distinct():
    r1 = _rec("scopus", "S1", "Functional movement disorders", doi="10.1212/cpj.0000000000000350")
    r2 = _rec("scopus", "S2", "Functional movement disorders", doi="10.1097/wco.0000000000000464")
    assert sts._classify(r1, r2, 0.0) is None


# ---------------------------------------------------------------------------
# Part 2: same_title_sweep — end-to-end sweep() on synthetic fixtures
# ---------------------------------------------------------------------------

def test_sweep_finds_true_dups_and_preprints():
    records = [
        _rec("scopus", "S1", "Hysteria around the world", doi="10.1159/000360062"),
        _rec("wos", "W1", "Hysteria around the World", doi="10.1159/000360062"),
        _rec("psycinfo", "P1", "Functional movement disorder",
             doi="10.3389/fpsyt.2025.1473913", year="2025"),
        _rec("wos", "W2", "Functional Movement Disorder",
             doi="10.1101/2024.07.23.24310881", year="2024"),
        # Distinct work, same generic title, no DOIs: must NOT be flagged.
        _rec("psycinfo", "P2", "Conversion disorder.", year="2017", authors="Loriedo, C."),
        _rec("psycinfo", "P3", "Conversion disorder.", year="2018", authors="Feinstein, A."),
        _rec("scopus", "S2", "Unrelated unique title nobody shares", doi="10.1/abc"),
    ]
    pairs = sts.sweep(records)
    classes = sorted(p["class"] for p in pairs)
    assert classes == ["PREPRINT_CANDIDATE", "TRUE_DUP_CANDIDATE"]
    titles = {p["title_norm"] for p in pairs}
    assert "conversion disorder" not in titles
    # Deterministic ordering: source_db then source_id.
    hp = [p for p in pairs if p["title_norm"] == "hysteria around the world"][0]
    assert hp["source_db1"] == "scopus" and hp["source_db2"] == "wos"
    assert hp["same_doi"] == "1"


def test_run_sweep_writes_csv():
    """run_sweep writes the full output schema and does NOT modify the input."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        inp = tmp_path / "records.csv"
        with open(inp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "source_db", "source_id", "doi", "title", "abstract", "authors",
                "journal", "year", "pub_date", "keywords", "mesh_terms",
                "pub_types", "url", "volume", "issue", "pages", "isbn", "issn",
                "retrieved_at"])
            w.writeheader()
            w.writerow({"source_db": "scopus", "source_id": "S1", "doi": "10.1159/000360062",
                        "title": "Hysteria around the world", "abstract": "x",
                        "authors": "Bogousslavsky J.", "year": "2016",
                        "journal": "", "pub_date": "", "keywords": "", "mesh_terms": "",
                        "pub_types": "", "url": "", "volume": "", "issue": "", "pages": "",
                        "isbn": "", "issn": "", "retrieved_at": ""})
            w.writerow({"source_db": "wos", "source_id": "W1", "doi": "10.1159/000360062",
                        "title": "Hysteria Around the World", "abstract": "x",
                        "authors": "Bogousslavsky, J.", "year": "2016",
                        "journal": "", "pub_date": "", "keywords": "", "mesh_terms": "",
                        "pub_types": "", "url": "", "volume": "", "issue": "", "pages": "",
                        "isbn": "", "issn": "", "retrieved_at": ""})
        before = inp.read_text(encoding="utf-8")
        out = tmp_path / "maybe_pairs_title_sweep.csv"
        pairs = sts.run_sweep(inp, out)
        assert len(pairs) == 1
        assert inp.read_text(encoding="utf-8") == before  # input untouched
        rows = list(csv.DictReader(open(out, encoding="utf-8")))
        assert list(rows[0].keys()) == sts.OUTPUT_COLUMNS
        assert rows[0]["class"] == "TRUE_DUP_CANDIDATE"
        assert rows[0]["same_doi"] == "1"
        assert rows[0]["title_norm"] == "hysteria around the world"


# ---------------------------------------------------------------------------
# Part 2: production validation — the frozen 2026-07-31 corpus
# ---------------------------------------------------------------------------

_CORPUS = Path(__file__).resolve().parent.parent / \
    "data" / "screening_corpus_2026-07-31" / "records_deduplicated_adjudicated.csv"


def test_production_corpus_sweep_validation():
    """The frozen corpus is the real test case: known leaked pairs must be
    flagged, generic-title groups must NOT be."""
    if not _CORPUS.is_file():
        # Dataset not present in this checkout (data dir may be gitignored);
        # skip without failing — the synthetic tests above carry the logic.
        print("SKIP: frozen corpus not present at", _CORPUS)
        return

    pairs = sts.sweep(sts._read_records(_CORPUS))
    by_title = {}
    for p in pairs:
        by_title.setdefault(p["title_norm"], []).append(p)

    titles = set(by_title)
    # --- KNOWN true-dup leaks that MUST be flagged ------------------------
    def assert_flagged(title_frag, label):
        hits = [t for t in titles if title_frag in t]
        assert hits, f"{label}: no same-title group found at all"
        for t in hits:
            assert any(p["class"] == "TRUE_DUP_CANDIDATE" for p in by_title[t]), \
                f"{label}: group {t!r} present but not flagged TRUE_DUP_CANDIDATE"

    assert_flagged("pseudoseizures trauma", "Pseudoseizures trauma (both DOIs missing)")
    assert_flagged("structural organization of the brain connectome",
                   "Structural Organization of the Brain Connectome (wos+wos)")
    assert_flagged("structural and functional brain network alterations",
                   "Structural and Functional Brain Network Alterations (wos+wos)")
    # Hysteria pairs (scopus article DOI vs wos multi-DOI field).
    hyst = [t for t in titles if t.startswith("hysteria around the world")]
    assert hyst, "Hysteria around the world: group missing"
    # 'Hysteria' today and tomorrow.
    assert any(t.startswith("hysteria today and tomorrow") for t in titles), \
        "'Hysteria' today and tomorrow group missing"

    # --- Generic-title groups MUST NOT be flagged -------------------------
    conv = [t for t in titles if t == "conversion disorder"]
    for t in conv:
        assert not any(p["class"] == "TRUE_DUP_CANDIDATE" for p in by_title[t]), \
            "Generic-title 'Conversion disorder.' groups must NOT be true-dup candidates"
    conv_prefix = [t for t in titles if t.startswith("conversion disorder")
                   and t != "conversion disorder"]
    for t in conv_prefix:
        for p in by_title[t]:
            if p["class"] == "TRUE_DUP_CANDIDATE":
                # Only acceptable if both records carry a real DOI (e.g. erratum groups).
                assert p["doi1"] and p["doi2"], \
                    f"missing-DOI true-dup flagged in generic-title group {t!r}"

    # --- Preprint candidates ----------------------------------------------
    preprints = [p for p in pairs if p["class"] == "PREPRINT_CANDIDATE"]
    assert len(preprints) >= 2, "expected the two known preprint pairs to be flagged"

    # --- Erratum groups with identical DOI: flagged as true-dup (correct
    # behavior — same-work records; humans decide). Just verify they exist.
    erratum_pairs = [p for p in pairs
                     if p["same_doi"] == "1" and "erratum" in p["title1"].lower()]
    assert erratum_pairs, "expected the same-DOI erratum group to appear as TRUE_DUP_CANDIDATE"


if __name__ == "__main__":
    test_pick_first_doi_wos_hysteria_multi_doi()
    test_pick_first_doi_single_token_passes_through_byte_identically()
    test_pick_first_doi_isbn_only_field_yields_none()
    test_pick_first_doi_isbn_token_before_article_doi()
    test_pick_first_doi_two_article_dois_keeps_first()
    test_pick_first_doi_isbn_case_insensitive()
    test_pick_first_doi_bare_isbn_single_token_untouched()
    test_import_ris_hysteria_records_doi()
    test_import_ris_single_doi_record_unchanged()
    test_import_ris_empty_doi_record()
    test_import_ris_wos_book_chapter_figshare_not_subsumed()
    test_normalize_title_strips_punct_case_whitespace()
    test_author_last_names_formats()
    test_classify_same_doi_true_dup()
    test_classify_missing_doi_is_unknown_never_equal()
    test_classify_missing_doi_with_year_and_author_overlap()
    test_classify_missing_doi_year_mismatch()
    test_classify_missing_doi_author_mismatch()
    test_classify_abstract_similarity_threshold()
    test_classify_preprint_pairs()
    test_classify_different_dois_both_non_preprint_distinct()
    test_sweep_finds_true_dups_and_preprints()
    test_run_sweep_writes_csv()
    test_production_corpus_sweep_validation()
    print("\n=== All tests passed! ===")
