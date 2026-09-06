"""Hardening tests for issue #8 Copilot-review findings (C1, C5).

C1: The PubMed MeSH branch must not emit a double "AND" when both the
    language filter and the human filter are disabled — a valid config
    combination when ``use_mesh`` is true (e.g. a full-text recall search).
C5: ``_term_set_lookup()`` must reject scalar-string term sets with a clear
    error instead of silently coercing them into per-character lists.
"""

import pytest

from fnd_meta_search import (
    SearchConfig,
    _term_set_lookup,
    build_pubmed_query,
)


def _mesh_config(**overrides) -> SearchConfig:
    """Minimal MeSH-mode PubMed config, overridable per test."""
    kwargs = dict(
        mode="custom",
        date_start=None,
        date_end="2026/07/31",
        language_filter=True,
        mri_fallback=False,
        pubmed_use_mesh=True,
        pubmed_use_exclusions=True,
        pubmed_use_human_filter=True,
        block_a=["functional neurological disorder*"],
        block_b=["neuroimaging"],
    )
    kwargs.update(overrides)
    return SearchConfig(**kwargs)


def test_c1_no_double_and_when_all_pubmed_filters_disabled():
    # C1: use_mesh=true + language_filter=false + pubmed_use_human_filter=false
    # previously produced the date filter's leading "AND " colliding with the
    # return template's own "AND" -> "... AND AND (...)". It must not.
    config = _mesh_config(language_filter=False, pubmed_use_human_filter=False)
    q = build_pubmed_query(config)
    assert "AND AND" not in q
    # Date filter survives, joined by a single "AND".
    assert 'AND ("1800/01/01"[Date - Publication]' in q
    # And it must not carry a spurious leading "AND " of its own.
    assert '("1800/01/01"[Date - Publication]' in q


def test_c1_exclusions_still_applied_without_filters():
    config = _mesh_config(language_filter=False, pubmed_use_human_filter=False)
    q = build_pubmed_query(config)
    assert 'NOT ("Editorial"[Publication Type]' in q


def test_c1_single_filter_still_byte_faithful():
    # When one filter is active the pre-existing separator behaviour must be
    # preserved (single "AND" between the core filter and the date filter).
    config = _mesh_config(language_filter=True, pubmed_use_human_filter=False)
    q = build_pubmed_query(config)
    assert "(English[Language]) AND (\"1800/01/01\"[Date - Publication]" in q
    assert "AND AND" not in q


def test_c5_raises_on_scalar_string_term_set():
    term_sets = {"fnd_terms": "functional neurological disorder"}
    with pytest.raises(ValueError, match="must be a list"):
        _term_set_lookup(term_sets, "fnd_terms")


def test_c5_list_term_set_ok():
    term_sets = {"fnd_terms": ["a", "b"]}
    assert _term_set_lookup(term_sets, "fnd_terms") == ["a", "b"]


def test_c5_missing_key_still_raises():
    with pytest.raises(ValueError, match="unknown term_set"):
        _term_set_lookup({}, "nope")
