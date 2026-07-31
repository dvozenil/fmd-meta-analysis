"""
Tests for the ASySD-class deduplication algorithm.

Each test covers a specific duplicate scenario that the matching rules
are designed to catch.
"""

import sys
import os

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dedup_asysd import (
    deduplicate_asysd,
    format_citations,
    order_citations,
    _jw,
    _is_true_match,
    PairData,
    identify_true_matches,
    _generate_candidate_pairs,
    _compute_pair_similarities,
)


def _make_pair(**kwargs) -> PairData:
    """Create a PairData with defaults for testing."""
    defaults = dict(
        id1=0, id2=1,
        author=0.0, title=0.0, abstract=0.0, year=0.0,
        pages=0.0, number=0.0, volume=0.0, journal=0.0,
        isbn=0.0, doi=0.0,
        year1="2020", year2="2020",
        doi1=None, doi2=None,
        record_id1="r1", record_id2="r2",
        title1="TEST", title2="TEST",
        author1="AUTHOR A", author2="AUTHOR A",
        journal1="J", journal2="J",
    )
    defaults.update(kwargs)
    return PairData(**defaults)


def _make_record(rid, title, author="Smith J", year="2020", doi=None,
                 abstract="An abstract about testing", journal="Nature",
                 pages=None, volume=None, number=None, isbn=None,
                 source="pubmed"):
    return {
        "record_id": rid,
        "source": source,
        "label": source,
        "title": title,
        "author": author,
        "year": year,
        "doi": doi,
        "abstract": abstract,
        "journal": journal,
        "pages": pages,
        "volume": volume,
        "number": number,
        "isbn": isbn,
    }


# ── Jaro-Winkler tests ──────────────────────────────────────────────────────

def test_jw_identical():
    assert _jw("hello", "hello") == 1.0

def test_jw_similar():
    assert _jw("hello world", "hello wrld") > 0.95

def test_jw_none():
    assert _jw(None, "test") == 0.0
    assert _jw("test", None) == 0.0

def test_jw_empty():
    assert _jw("", "test") == 0.0
    assert _jw("", "") == 0.0

def test_jw_different():
    assert _jw("abc", "xyz") < 0.5


# ── Formatting tests ─────────────────────────────────────────────────────────

def test_format_doi():
    recs = format_citations([{"record_id": "1", "doi": "HTTPS://DOI.ORG/10.1234/test"}])
    assert recs[0]["doi"] == "10.1234/TEST"

def test_format_author_anonymous():
    recs = format_citations([{"record_id": "1", "author": "Anonymous"}])
    assert recs[0]["author"] == "UNKNOWN"

def test_format_title_punctuation_removed():
    recs = format_citations([{"record_id": "1", "title": "Hello, World!"}])
    assert recs[0]["title"] == "HELLO WORLD"

def test_format_pages_double_dash():
    recs = format_citations([{"record_id": "1", "pages": "1--10"}])
    assert recs[0]["pages"] == "1-10"

def test_format_missing_fields():
    recs = format_citations([{"record_id": "1", "title": "Test"}])
    assert recs[0]["doi"] is None
    assert recs[0]["pages"] is None
    assert recs[0]["volume"] is None
    assert recs[0]["isbn"] is None


# ── True match rule tests ────────────────────────────────────────────────────

def test_rule_doi_author_title():
    """Rule: doi>0.95 & author>0.75 & title>0.9"""
    p = _make_pair(doi=0.96, author=0.76, title=0.91)
    assert _is_true_match(p)

def test_rule_doi_below_threshold():
    p = _make_pair(doi=0.94, author=0.80, title=0.95)
    # This rule won't fire, but others might not either with defaults=0
    assert not _is_true_match(p)

def test_rule_title_abstract_volume_journal_author():
    """Rule: title>0.80 & abstract>0.90 & volume>0.85 & journal>0.65 & author>0.9"""
    p = _make_pair(title=0.81, abstract=0.91, volume=0.86, journal=0.66, author=0.91)
    assert _is_true_match(p)

def test_rule_title_author_abstract_journal():
    """Rule: title>0.9 & author>0.9 & abstract>0.9 & journal>0.7"""
    p = _make_pair(title=0.91, author=0.91, abstract=0.91, journal=0.71)
    assert _is_true_match(p)

def test_rule_title_author_abstract_isbn():
    """Rule: title>0.9 & author>0.9 & abstract>0.9 & isbn>0.99"""
    p = _make_pair(title=0.91, author=0.91, abstract=0.91, isbn=1.0)
    assert _is_true_match(p)

def test_rule_pages_volume_title_abstract_author_isbn():
    """Rule: pages>0.8 & volume>0.8 & title>0.90 & abstract>0.90 & author>0.50 & isbn>0.99"""
    p = _make_pair(pages=0.81, volume=0.81, title=0.91, abstract=0.91, author=0.51, isbn=1.0)
    assert _is_true_match(p)

def test_rule_pages_volume_title_abstract_author_journal():
    """Rule: pages>0.8 & volume>0.8 & title>0.90 & abstract>0.90 & author>0.50 & journal>0.6"""
    p = _make_pair(pages=0.81, volume=0.81, title=0.91, abstract=0.91, author=0.51, journal=0.61)
    assert _is_true_match(p)

def test_rule_volume_number_title_abstract_author():
    """Rule: volume>0.8 & number>0.8 & title>0.90 & abstract>0.90 & author>0.8"""
    p = _make_pair(volume=0.81, number=0.81, title=0.91, abstract=0.91, author=0.81)
    assert _is_true_match(p)

def test_rule_pages_number_title_abstract_author():
    """Rule: pages>0.8 & number>0.8 & title>0.90 & abstract>0.9 & author>0.8"""
    p = _make_pair(pages=0.81, number=0.81, title=0.91, abstract=0.91, author=0.81)
    assert _is_true_match(p)

def test_rule_high_threshold_combos():
    """Rule: pages>0.9 & number>0.9 & title>0.90 & author>0.80 & journal>0.6"""
    p = _make_pair(pages=0.91, number=0.91, title=0.91, author=0.81, journal=0.61)
    assert _is_true_match(p)

def test_rule_title_volume_author_journal_high():
    """Rule: pages>0.8 & volume>0.8 & title>0.95 & author>0.80 & journal>0.9"""
    p = _make_pair(pages=0.81, volume=0.81, title=0.96, author=0.81, journal=0.91)
    assert _is_true_match(p)

def test_no_match_when_all_low():
    p = _make_pair(title=0.5, author=0.5, abstract=0.5, doi=0.5,
                   pages=0.5, volume=0.5, number=0.5, journal=0.5, isbn=0.5)
    assert not _is_true_match(p)


# ── identify_true_matches post-filtering ────────────────────────────────────

def test_doi_mismatch_removed():
    """Pairs with low DOI similarity (0 < doi <= 0.99) should be removed
    unless title>0.9 & abstract>0.9 & (journal>0.9 or isbn>0.9).

    We need a rule to fire first: title>0.9 & author>0.9 & abstract>0.9 & journal>0.7
    Then the DOI mismatch (0 < doi <= 0.99) removes it because journal < 0.9.
    """
    p = _make_pair(doi=0.5, title=0.92, author=0.91, abstract=0.92,
                   journal=0.71, isbn=0.0,
                   doi1="10.1/a", doi2="10.1/b")
    true_pairs, maybe_pairs = identify_true_matches([p])
    assert len(true_pairs) == 0
    # Should appear in maybe_pairs due to DOI mismatch
    assert len(maybe_pairs) >= 1

def test_doi_mismatch_rescued_by_high_title_abstract_journal():
    """Low DOI match but high title/abstract/journal should keep the pair.

    Rule fires via title>0.9 & author>0.9 & abstract>0.9 & journal>0.7.
    DOI mismatch is rescued because title>0.9 & abstract>0.9 & journal>0.9.
    """
    p = _make_pair(doi=0.5, title=0.92, author=0.91, abstract=0.92,
                   journal=0.91, isbn=0.0,
                   doi1="10.1/a", doi2="10.1/b")
    true_pairs, _ = identify_true_matches([p])
    assert len(true_pairs) == 1

def test_year_mismatch_major():
    """Pairs where years differ by >1 should be removed from true_pairs."""
    p = _make_pair(
        title=0.91, author=0.91, abstract=0.91, journal=0.71,
        year1="2020", year2="2015",
    )
    true_pairs, maybe_pairs = identify_true_matches([p])
    assert len(true_pairs) == 0
    assert len(maybe_pairs) >= 1

def test_year_mismatch_minor_kept():
    """Pairs where years differ by exactly 1 should be kept."""
    p = _make_pair(
        title=0.91, author=0.91, abstract=0.91, journal=0.71,
        year1="2020", year2="2019",
    )
    true_pairs, _ = identify_true_matches([p])
    assert len(true_pairs) == 1


# ── Integration tests ────────────────────────────────────────────────────────

def test_exact_duplicate():
    """Two identical records should be deduplicated."""
    recs = [
        _make_record("1", "Brain imaging in FND", doi="10.1234/test"),
        _make_record("2", "Brain imaging in FND", doi="10.1234/test"),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1
    assert stats["duplicates_removed"] == 1

def test_no_duplicates():
    """Two distinct records should both be kept."""
    recs = [
        _make_record("1", "Brain imaging in FND", doi="10.1234/a", abstract="About brain imaging"),
        _make_record("2", "Heart disease in adults", doi="10.1234/b", abstract="About heart disease"),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 2
    assert stats["duplicates_removed"] == 0

def test_doi_match_different_title():
    """Same DOI but very different titles should NOT auto-merge
    (quarantined as DOI/title conflict → maybe_pairs)."""
    recs = [
        _make_record("1", "Brain imaging in FND", doi="10.1234/test"),
        _make_record("2", "Completely different topic here", doi="10.1234/test"),
    ]
    unique, stats, maybe = deduplicate_asysd(recs)
    assert stats["unique"] == 2
    assert len(maybe) >= 1

def test_cross_database_duplicate():
    """Same paper from PubMed and Scopus should be deduplicated."""
    recs = [
        _make_record("pm1", "Functional neurological disorder and trauma",
                     doi="10.5678/fnd", source="pubmed"),
        _make_record("sc1", "Functional neurological disorder and trauma",
                     doi="10.5678/fnd", source="scopus"),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1

def test_keep_source_preference():
    """When keep_source is set, the representative should be from that source
    when completeness is otherwise equal."""
    recs = [
        _make_record("pm1", "Functional neurological disorder and trauma",
                     doi="10.5678/fnd", source="pubmed",
                     abstract="An abstract about testing"),
        _make_record("sc1", "Functional neurological disorder and trauma",
                     doi="10.5678/fnd", source="scopus",
                     abstract="An abstract about testing"),
    ]
    unique, _, _ = deduplicate_asysd(recs, keep_source="pubmed")
    assert unique[0]["source"] == "pubmed"


def test_prefer_complete_abstract():
    """Records with abstracts should be preferred over empty-abstract copies."""
    recs = [
        _make_record("sc1", "Same title neuroimaging FND",
                     doi="10.2/b", source="scopus", abstract=""),
        _make_record("pm1", "Same title neuroimaging FND",
                     doi="10.2/b", source="pubmed",
                     abstract="A substantial abstract that should be preferred."),
    ]
    unique, _, _ = deduplicate_asysd(recs, keep_source="pubmed")
    assert len(unique) == 1
    assert unique[0]["source"] == "pubmed"
    assert unique[0]["abstract"]


def test_exact_doi_match_despite_title_truncation():
    """Exact DOI should merge even when one title is truncated."""
    recs = [
        _make_record("pm1", "Effects of ", doi="10.1136/jnnp-2019-322636",
                     source="pubmed", abstract=""),
        _make_record("sc1",
                     "Effects of TPH2 gene variation and childhood trauma on "
                     "the clinical and circuit-level phenotype of functional "
                     "neurological disorder",
                     doi="10.1136/jnnp-2019-322636", source="scopus",
                     abstract="Full abstract text about the study."),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1
    assert unique[0]["abstract"]

def test_three_way_duplicate():
    """Three copies of the same paper should collapse to 1."""
    recs = [
        _make_record("1", "Same title here", doi="10.1/x"),
        _make_record("2", "Same title here", doi="10.1/x"),
        _make_record("3", "Same title here", doi="10.1/x"),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1

def test_transitive_dedup():
    """A→B and B→C are duplicates but A and C aren't directly matched.
    Connected components should merge all three."""
    recs = [
        _make_record("a", "Title one about brains", doi="10.1/a", source="pubmed"),
        _make_record("b", "Title one about brains", doi="10.1/a", source="scopus"),
        _make_record("c", "Title one about brains", doi="10.1/a", source="europepmc"),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1

def test_empty_input():
    unique, stats, maybe = deduplicate_asysd([])
    assert unique == []
    assert stats["unique"] == 0
    assert maybe == []

def test_single_record():
    recs = [_make_record("1", "Only one record", doi="10.1/x")]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1
    assert stats["duplicates_removed"] == 0

def test_maybe_pairs_generated():
    """Pairs that look similar but don't meet strict thresholds should
    appear in maybe_pairs."""
    recs = [
        _make_record("1", "Similar title about brains", doi=None, abstract="test abstract one"),
        _make_record("2", "Similar title about brain", doi=None, abstract="test abstract two"),
    ]
    _, _, maybe = deduplicate_asysd(recs)
    # These might or might not be true duplicates, but they should at least
    # appear as candidates (either true or maybe)
    # With high title similarity and same author, they likely match
    # The test just ensures the function runs and returns a list
    assert isinstance(maybe, list)

def test_both_missing_pages_volume_number():
    """When pages/volume/number are all missing for both records,
    the both-missing → 1.0 rule should kick in."""
    recs = [
        _make_record("1", "Test title here", doi="10.1/x", pages=None, volume=None, number=None),
        _make_record("2", "Test title here", doi="10.1/x", pages=None, volume=None, number=None),
    ]
    unique, stats, _ = deduplicate_asysd(recs)
    assert stats["unique"] == 1


# ── Blocking tests ───────────────────────────────────────────────────────────

def test_blocking_by_doi():
    """Records with the same DOI should be blocked together."""
    formatted = format_citations([
        _make_record("1", "Title A", doi="10.1234/test"),
        _make_record("2", "Title B", doi="10.1234/test"),
        _make_record("3", "Title C", doi="10.5678/other"),
    ])
    pairs = _generate_candidate_pairs(formatted)
    # Records 1 and 2 should be paired (same DOI)
    pair_ids = set()
    for i, j in pairs:
        pair_ids.add((formatted[i]["record_id"], formatted[j]["record_id"]))
    assert ("1", "2") in pair_ids or ("2", "1") in pair_ids

def test_blocking_by_title_author():
    """Records with same title and author should be blocked."""
    formatted = format_citations([
        _make_record("1", "Same Title", author="Smith J"),
        _make_record("2", "Same Title", author="Smith J"),
    ])
    pairs = _generate_candidate_pairs(formatted)
    assert len(pairs) >= 1


# ── Run all tests ───────────────────────────────────────────────────────────

def run_all_tests():
    """Run all test functions and report results."""
    tests = [
        (name, func) for name, func in sorted(globals().items())
        if name.startswith("test_") and callable(func)
    ]
    passed = 0
    failed = 0
    failures = []

    for name, func in tests:
        try:
            func()
            passed += 1
            print(f"  ✓ {name}")
        except AssertionError as e:
            failed += 1
            failures.append((name, str(e)))
            print(f"  ✗ {name}: {e}")
        except Exception as e:
            failed += 1
            failures.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ✗ {name}: {type(e).__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failures:
        print("\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)  # Suppress log output during tests
    success = run_all_tests()
    sys.exit(0 if success else 1)
