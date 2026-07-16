"""Unit tests for ScopusClient._parse() — issue #3 fix.

Tests that authors and bibliographic fields are correctly extracted
from both COMPLETE and STANDARD view responses.
"""

import sys
from pathlib import Path

# Allow running from repo root without installation
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fnd_meta_search import ScopusClient, Record


# ---------------------------------------------------------------------------
# Mock API response — COMPLETE view (full author list)
# ---------------------------------------------------------------------------
COMPLETE_ENTRY = {
    "dc:identifier": "SCOPUS_ID:84991662109",
    "eid": "2-s2.0-84991662109",
    "dc:title": "Early childhood trauma and hippocampal volumes",
    "prism:doi": "10.1016/j.yebeh.2016.09.015",
    "prism:publicationName": "Epilepsy and Behavior",
    "prism:coverDate": "2016-11-01",
    "prism:volume": "64",
    "prism:issueIdentifier": "Pt B",
    "prism:pageRange": "150-157",
    "prism:issn": "1525-5050",
    "prism:isbn": "",
    "dc:creator": "Smith J.",
    "author": [
        {"@auid": "56482983700", "authname": "Smith J.",
         "given-name": "John", "surname": "Smith"},
        {"@auid": "7202784561", "authname": "Jones A.",
         "given-name": "Alice", "surname": "Jones"},
        {"@auid": "57201234567", "authname": "Brown B.",
         "given-name": "Bob", "surname": "Brown"},
    ],
    "authkeywords": "trauma | PNES | hippocampus",
    "link": [
        {"@ref": "scopus", "@href": "https://www.scopus.com/inward/record.uri?scp=84991662109"},
        {"@ref": "self", "@href": "https://api.elsevier.com/content/abstract/scopus_id/84991662109"},
    ],
}

# ---------------------------------------------------------------------------
# Mock API response — STANDARD view (first author only)
# ---------------------------------------------------------------------------
STANDARD_ENTRY = {
    "dc:identifier": "SCOPUS_ID:84991662109",
    "eid": "2-s2.0-84991662109",
    "dc:title": "Early childhood trauma and hippocampal volumes",
    "prism:doi": "10.1016/j.yebeh.2016.09.015",
    "prism:publicationName": "Epilepsy and Behavior",
    "prism:coverDate": "2016-11-01",
    "prism:volume": "64",
    "prism:issueIdentifier": "Pt B",
    "prism:pageRange": "150-157",
    "prism:issn": "1525-5050",
    "dc:creator": "Smith J.",
    "authkeywords": "trauma | PNES | hippocampus",
    "link": [
        {"@ref": "scopus", "@href": "https://www.scopus.com/inward/record.uri?scp=84991662109"},
    ],
}

# Minimal entry with no authors at all
EMPTY_ENTRY = {
    "dc:identifier": "SCOPUS_ID:12345",
    "dc:title": "Some article",
    "prism:coverDate": "2020-01-01",
}


def test_complete_view_authors():
    """COMPLETE view should extract full author list."""
    rec = ScopusClient._parse(COMPLETE_ENTRY)
    assert rec.authors == ["Smith J.", "Jones A.", "Brown B."], \
        f"Expected 3 authors, got {rec.authors}"
    assert rec.source_db == "scopus"
    assert rec.source_id == "84991662109"
    assert rec.doi == "10.1016/j.yebeh.2016.09.015"
    print(f"✓ COMPLETE view: {len(rec.authors)} authors parsed")


def test_standard_view_authors():
    """STANDARD view should fall back to dc:creator (first author)."""
    rec = ScopusClient._parse(STANDARD_ENTRY)
    assert len(rec.authors) == 1, \
        f"Expected 1 author (dc:creator fallback), got {rec.authors}"
    assert rec.authors[0] == "Smith J.", \
        f"Expected 'Smith J.', got '{rec.authors[0]}'"
    print(f"✓ STANDARD view: dc:creator fallback works -> {rec.authors[0]}")


def test_empty_authors():
    """Entry with no author data should produce empty list, not crash."""
    rec = ScopusClient._parse(EMPTY_ENTRY)
    assert rec.authors == [], f"Expected empty list, got {rec.authors}"
    print("✓ Empty authors: no crash, returns []")


def test_bibliographic_fields_complete():
    """COMPLETE view should extract volume, issue, pages, issn."""
    rec = ScopusClient._parse(COMPLETE_ENTRY)
    assert rec.volume == "64", f"Expected volume '64', got '{rec.volume}'"
    assert rec.issue == "Pt B", f"Expected issue 'Pt B', got '{rec.issue}'"
    assert rec.pages == "150-157", f"Expected pages '150-157', got '{rec.pages}'"
    assert rec.issn == "1525-5050", f"Expected issn, got '{rec.issn}'"
    print(f"✓ Bibliographic fields: vol={rec.volume}, issue={rec.issue}, "
          f"pages={rec.pages}, issn={rec.issn}")


def test_bibliographic_fields_standard():
    """STANDARD view should also extract volume, issue, pages, issn."""
    rec = ScopusClient._parse(STANDARD_ENTRY)
    assert rec.volume == "64", f"Expected volume '64', got '{rec.volume}'"
    assert rec.issue == "Pt B", f"Expected issue 'Pt B', got '{rec.issue}'"
    assert rec.pages == "150-157", f"Expected pages '150-157', got '{rec.pages}'"
    assert rec.issn == "1525-5050", f"Expected issn, got '{rec.issn}'"
    print(f"✓ STANDARD bibliographic: vol={rec.volume}, issue={rec.issue}, "
          f"pages={rec.pages}, issn={rec.issn}")


def test_keywords_parsed():
    """Keywords should be split on pipe character."""
    rec = ScopusClient._parse(COMPLETE_ENTRY)
    assert rec.keywords == ["trauma", "PNES", "hippocampus"], \
        f"Got {rec.keywords}"
    print(f"✓ Keywords: {rec.keywords}")


def test_url_extraction():
    """URL should be extracted from link array with @ref=scopus."""
    rec = ScopusClient._parse(COMPLETE_ENTRY)
    assert "scp=84991662109" in rec.url, f"URL mismatch: {rec.url}"
    print(f"✓ URL: {rec.url[:60]}...")


def test_isbn_list_handling():
    """ISBN returned as a list should be joined with semicolons."""
    entry = dict(COMPLETE_ENTRY)
    entry["prism:isbn"] = ["978-3-16-148410-0", "978-3-16-148411-7"]
    rec = ScopusClient._parse(entry)
    assert rec.isbn == "978-3-16-148410-0; 978-3-16-148411-7", \
        f"Got {rec.isbn}"
    print(f"✓ ISBN list handling: {rec.isbn}")


def test_isbn_list_of_dicts():
    """ISBN/ISSN may be returned as a list of {"$": value} dicts.

    Regression test: Scopus (XML→JSON) sometimes wraps prism:isbn items in
    dicts, which previously crashed '; '.join() with
    'TypeError: expected str instance, dict found'.
    """
    entry = dict(COMPLETE_ENTRY)
    entry["prism:isbn"] = [{"$": "978-3-16-148410-0"}, {"$": "978-3-16-148411-7"}]
    entry["prism:issn"] = [{"$": "1525-5050"}]
    rec = ScopusClient._parse(entry)
    assert rec.isbn == "978-3-16-148410-0; 978-3-16-148411-7", f"Got {rec.isbn}"
    assert rec.issn == "1525-5050", f"Got {rec.issn}"
    print(f"✓ ISBN/ISSN list-of-dicts: isbn={rec.isbn!r} issn={rec.issn!r}")


def test_record_has_new_fields():
    """Record dataclass should have volume, issue, pages, isbn, issn fields."""
    fields = Record.__dataclass_fields__
    for field_name in ("volume", "issue", "pages", "isbn", "issn"):
        assert field_name in fields, f"Missing field: {field_name}"
    print("✓ Record dataclass has all new fields: volume, issue, pages, isbn, issn")


# ---------------------------------------------------------------------------
# Abstract Retrieval author parsing (full author list)
# ---------------------------------------------------------------------------
ABSTRACT_AUTHORS_NODE = {
    "author": [
        {"@auid": "56482983700",
         # Top-level indexed-name carries ALL initials (Scopus's canonical
         # form, matching dc:creator); preferred-name truncates to one.
         "ce:indexed-name": "Johnstone B.C.",
         "ce:surname": "Johnstone", "ce:initials": "B.C.",
         "preferred-name": {"ce:indexed-name": "Johnstone B.",
                             "ce:surname": "Johnstone",
                             "ce:given-name": "Brett C"}},
        {"@auid": "7202784561",
         "ce:indexed-name": "Jones A.D.",
         "ce:surname": "Jones", "ce:initials": "A.D.",
         "preferred-name": {"ce:indexed-name": "Jones A.",
                             "ce:surname": "Jones",
                             "ce:given-name": "Alice D"}},
    ]
}


def test_parse_abstract_authors_full():
    """Abstract Retrieval authors node should yield full canonical name list.

    The top-level ``ce:indexed-name`` (all initials) is preferred over the
    truncated ``preferred-name.ce:indexed-name``, for consistency with the
    first-author string produced from ``dc:creator``.
    """
    names = ScopusClient._parse_abstract_authors(ABSTRACT_AUTHORS_NODE)
    assert names == ["Johnstone B.C.", "Jones A.D."], f"Got {names}"
    print(f"✓ Abstract authors (full list): {names}")


def test_parse_abstract_authors_fallback_surname():
    """Authors missing ce:indexed-name should be built from surname + given."""
    node = {"author": [{"preferred-name": {"ce:surname": "Garcia", "ce:given-name": "Maria"}}]}
    names = ScopusClient._parse_abstract_authors(node)
    assert names == ["Garcia Maria"], f"Got {names}"
    print(f"✓ Abstract authors (surname fallback): {names}")


def test_parse_abstract_authors_single_dict():
    """A lone author returned as a dict (not a list) should still parse."""
    node = {"author": {"preferred-name": {"ce:indexed-name": "Solo A."}}}
    names = ScopusClient._parse_abstract_authors(node)
    assert names == ["Solo A."], f"Got {names}"
    print(f"✓ Abstract authors (single-dict): {names}")


def test_parse_abstract_authors_empty():
    """Missing/empty authors node should return [] without crashing."""
    assert ScopusClient._parse_abstract_authors(None) == []
    assert ScopusClient._parse_abstract_authors({}) == []
    assert ScopusClient._parse_abstract_authors({"author": []}) == []
    print("✓ Abstract authors (empty): []")


if __name__ == "__main__":
    test_complete_view_authors()
    test_standard_view_authors()
    test_empty_authors()
    test_bibliographic_fields_complete()
    test_bibliographic_fields_standard()
    test_keywords_parsed()
    test_url_extraction()
    test_isbn_list_handling()
    test_isbn_list_of_dicts()
    test_record_has_new_fields()
    test_parse_abstract_authors_full()
    test_parse_abstract_authors_fallback_surname()
    test_parse_abstract_authors_single_dict()
    test_parse_abstract_authors_empty()
    print("\n=== All tests passed! ===")
