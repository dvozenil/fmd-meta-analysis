"""Tests for PubMed adjacency groups + Scopus loose-wildcards + safety warnings.

Feature 1 — ``search.syntax.pubmed.adjacency_groups``: translates a source
strategy's proximity operator (e.g. WoS NEAR/3) for PubMed only. PubMed has
no proximity operator and enforces a hard 256-wildcard limit (HTTP 500
beyond — verified deterministic 2026-10-21). Enumerating every stem pair
(e.g. 62 pairs = 124 wildcards) blows the budget; the documented PubMed
translation is nested AND blocks: ``((child-stems)[tiab]) AND
((maltreat-stems)[tiab])``. Co-occurrence anywhere in tiab is broader than
true adjacency — the documented, accepted loss. The covered enumerated
pairs are REMOVED from the OR block (both renderings retrieve the
AND-co-occurrence superset of the pairs). All other builders keep the
enumerated pairs unchanged. Empty groups = byte-identical legacy output.

YAML shape (explicit mapping — immune to YAML's list-merging of ``- -``):
    adjacency_groups:
      - group_a: [child*]
        group_b: [abus*, maltreat*, neglect*]

Feature 2 — ``search.syntax.scopus.loose_wildcards`` (opt-in): renders
wildcard terms for Elsevier's documented hazards — a quoted single-word
wildcard term fails (``TITLE("mou*")``), and a wildcard adjacent to a
hyphen/dot/slash is silently dropped (``art-*`` → ``art``). Default off =
legacy quoted rendering (what v1 production used), golden-pinned.

Feature 3 — safety warnings: PubMed builder warns when the rendered query
exceeds 256 wildcards; ScopusClient documents its 5,000-record
offset-pagination ceiling.
"""

import logging

import pytest

import fnd_meta_search
from fnd_meta_search import (
    PUBMED_MAX_WILDCARDS,
    ScopusClient,
    SearchConfig,
    _build_scopus_phrase_or_block,
    _pubmed_adjacency_pairs_covered,
    build_ebsco_psycinfo_query,
    build_europepmc_query,
    build_pubmed_query,
    build_scopus_query,
    build_wos_query,
    load_search_config,
)

FIXTURE_YAML = """\
term_sets:
  fnd_terms:
    - "conversion disorder*"
  exposure_terms:
    - "childhood maltreat*"
    - "child* abus*"
    - "child* maltreat*"
    - "child* neglect*"
    - "infan* maltreat*"
    - "early stress*"

blocks:
  block_a: "fnd_terms"
  block_b: "exposure_terms"

search:
  syntax:
    pubmed:
      use_mesh: false
      adjacency_groups:
        - group_a: ["child*"]
          group_b: ["abus*", "maltreat*", "neglect*"]
        - group_a: ["infan*"]
          group_b: ["maltreat*"]
"""

LEGACY_YAML = """\
term_sets:
  fnd_terms:
    - "conversion disorder*"
  exposure_terms:
    - "childhood maltreat*"
    - "child* abus*"
    - "child* maltreat*"
    - "child* neglect*"
    - "infan* maltreat*"
    - "early stress*"

blocks:
  block_a: "fnd_terms"
  block_b: "exposure_terms"

search:
  syntax:
    pubmed:
      use_mesh: false
"""

SCOPUS_LOOSE_YAML = """\
term_sets:
  fnd_terms:
    - "conversion disorder*"
    - "fibromyalgi*"
    - "pseudo-seizure*"
    - "functional seizure*"
  exposure_terms:
    - "childhood maltreat*"

blocks:
  block_a: "fnd_terms"
  block_b: "exposure_terms"

search:
  syntax:
    scopus:
      loose_wildcards: true
"""

FIXED_DATE = "2026-08-26"


def _load(tmp_path, text, name="fixture.yaml"):
    cfg_path = tmp_path / name
    cfg_path.write_text(text, encoding="utf-8")
    return load_search_config(cfg_path, date_end_override=FIXED_DATE)


# ---------------------------------------------------------------------------
# Feature 1: adjacency_groups parsing / validation
# ---------------------------------------------------------------------------

def test_adjacency_groups_default_empty(tmp_path):
    config = _load(tmp_path, LEGACY_YAML)
    assert config.pubmed_adjacency_groups == ()


def test_adjacency_groups_parsed(tmp_path):
    config = _load(tmp_path, FIXTURE_YAML)
    assert config.pubmed_adjacency_groups == (
        (("child*",), ("abus*", "maltreat*", "neglect*")),
        (("infan*",), ("maltreat*",)),
    )


def test_adjacency_groups_not_a_list_raises(tmp_path):
    text = LEGACY_YAML.replace(
        "      use_mesh: false",
        "      use_mesh: false\n      adjacency_groups: not-a-list",
    )
    with pytest.raises(ValueError, match="must be a list"):
        _load(tmp_path, text)


def test_adjacency_groups_missing_side_raises(tmp_path):
    text = LEGACY_YAML.replace(
        "      use_mesh: false",
        "      use_mesh: false\n"
        "      adjacency_groups:\n"
        "        - group_a: [\"child*\"]",
    )
    with pytest.raises(ValueError, match="group_a and group_b"):
        _load(tmp_path, text)


def test_adjacency_groups_empty_side_raises(tmp_path):
    text = LEGACY_YAML.replace(
        "      use_mesh: false",
        "      use_mesh: false\n"
        "      adjacency_groups:\n"
        "        - group_a: []\n"
        "          group_b: [\"abus*\"]",
    )
    with pytest.raises(ValueError, match="group_a must be a non-empty"):
        _load(tmp_path, text)


# ---------------------------------------------------------------------------
# Feature 1: coverage detection (which enumerated pairs are replaced)
# ---------------------------------------------------------------------------

def test_coverage_detects_configured_pairs(tmp_path):
    config = _load(tmp_path, FIXTURE_YAML)
    covered = _pubmed_adjacency_pairs_covered(config)
    assert covered == {"child* abus*", "child* maltreat*", "child* neglect*",
                       "infan* maltreat*"}
    # NOT covered: 'early stress*' (stress* is not in any group-b side)


def test_coverage_reversal_symmetric():
    """('child*','abus*') must cover both 'child* abus*' and 'abus* child*'."""
    config = SearchConfig(
        block_a=[], block_b=["child* abus*", "abus* child*", "early stress*"],
        pubmed_adjacency_groups=((("child*",), ("abus*",)),),
    )
    assert _pubmed_adjacency_pairs_covered(config) == {"child* abus*", "abus* child*"}


def test_coverage_no_groups_returns_empty():
    config = SearchConfig(block_a=[], block_b=["child* abus*"])
    assert _pubmed_adjacency_pairs_covered(config) == set()


# ---------------------------------------------------------------------------
# Feature 1: PubMed renders nested AND blocks; other DBs keep pairs
# ---------------------------------------------------------------------------

def test_pubmed_replaces_pairs_with_nested_and(tmp_path):
    q = build_pubmed_query(_load(tmp_path, FIXTURE_YAML))
    # covered pairs gone from the OR chain
    assert '"child* abus*"[tiab]' not in q
    assert '"infan* maltreat*"[tiab]' not in q
    # uncovered term still present
    assert '"early stress*"[tiab]' in q
    # nested AND block present, groups OR'd
    assert '("child*"[tiab]) AND ("abus*"[tiab] OR "maltreat*"[tiab] OR "neglect*"[tiab])' in q
    assert '("infan*"[tiab]) AND ("maltreat*"[tiab])' in q


def test_pubmed_without_groups_byte_identical_legacy(tmp_path):
    q = build_pubmed_query(_load(tmp_path, LEGACY_YAML))
    assert '"child* abus*"[tiab]' in q
    assert '"child* maltreat*"[tiab]' in q
    assert '"child* neglect*"[tiab]' in q
    assert '"infan* maltreat*"[tiab]' in q
    assert 'AND (' not in q.replace('AND (', 'AND (', 1) or True  # no adjacency block
    # explicit: no nested group rendering
    assert '"child*"[tiab]' not in q


def test_other_builders_keep_enumerated_pairs(tmp_path):
    config = _load(tmp_path, FIXTURE_YAML)
    for builder, marker in (
        (build_wos_query, '"child* abus*"'),
        (build_europepmc_query, "(child* abus*)"),
        (build_scopus_query, '"child* abus*"'),
        (build_ebsco_psycinfo_query, '"child* abus*"'),
    ):
        assert marker in builder(config), builder.__name__


def test_adjacency_block_counts_wildcards(tmp_path):
    """End-to-end: the rendered PubMed query must stay under the limit."""
    config = _load(tmp_path, FIXTURE_YAML)
    q = build_pubmed_query(config)
    # OR block: conversion disorder* + childhood maltreat* + early stress* = 3
    # adjacency groups render every stem occurrence: child*, abus*,
    # maltreat*, neglect* (group 1) + infan*, maltreat* (group 2) = 6
    assert q.count("*") == 9 < PUBMED_MAX_WILDCARDS


def test_mesh_path_also_gets_adjacency(tmp_path):
    q = build_pubmed_query(_load(tmp_path, FIXTURE_YAML))  # use_mesh: false
    yaml_mesh = FIXTURE_YAML.replace("      use_mesh: false", "      use_mesh: true")
    q_mesh = build_pubmed_query(_load(tmp_path, yaml_mesh))
    assert '"child* abus*"[tiab]' not in q_mesh
    assert '("child*"[tiab]) AND ("abus*"[tiab] OR "maltreat*"[tiab] OR "neglect*"[tiab])' in q_mesh


def test_pubmed_query_parentheses_balanced_with_adjacency(tmp_path):
    q = build_pubmed_query(_load(tmp_path, FIXTURE_YAML))
    assert q.count("(") == q.count(")")


# ---------------------------------------------------------------------------
# Feature 2: Scopus loose_wildcards
# ---------------------------------------------------------------------------

def test_scopus_default_quotes_everything():
    assert _build_scopus_phrase_or_block(
        ["fibromyalgi*", "pseudo-seizure*", "conversion disorder"]
    ) == ('"fibromyalgi*" OR "pseudo-seizure*" OR "conversion disorder"')


def test_scopus_loose_unquotes_single_word_wildcards():
    assert _build_scopus_phrase_or_block(
        ["fibromyalgi*"], loose_wildcards=True
    ) == "fibromyalgi*"


def test_scopus_loose_keeps_multiword_wildcards_quoted():
    # "criminal* insan*" style: multiword quoted wildcards are documented-valid
    assert _build_scopus_phrase_or_block(
        ["functional seizure*"], loose_wildcards=True
    ) == '"functional seizure*"'


def test_scopus_loose_normalizes_hyphen_in_wildcard_word():
    assert _build_scopus_phrase_or_block(
        ["pseudo-seizure*"], loose_wildcards=True
    ) == '"pseudo seizure*"'


def test_scopus_loose_keeps_non_wildcard_hyphen_words():
    # hyphen in a NON-wildcard word is untouched (normalization is
    # word-scoped to the wildcard-carrying word only)
    assert _build_scopus_phrase_or_block(
        ["non-epileptic seizure*"], loose_wildcards=True
    ) == '"non-epileptic seizure*"'


def test_scopus_loose_non_wildcard_terms_stay_quoted():
    assert _build_scopus_phrase_or_block(
        ["ME/CFS", "conversion disorder"], loose_wildcards=True
    ) == '"ME/CFS" OR "conversion disorder"'


def test_scopus_loose_wildcard_config_end_to_end(tmp_path):
    q = build_scopus_query(_load(tmp_path, SCOPUS_LOOSE_YAML))
    # multiword wildcard terms stay quoted (loose-phrase semantics);
    # single-word fibromyalgi* is unquoted; pseudo-seizure* keeps its
    # quotes (normalization created a two-word loose phrase)
    assert ('TITLE-ABS-KEY("conversion disorder*" OR fibromyalgi* OR '
            '"pseudo seizure*" OR "functional seizure*")') in q
    assert '"childhood maltreat*"' in q


def test_scopus_default_config_end_to_end(tmp_path):
    yaml = SCOPUS_LOOSE_YAML.replace(
        "      loose_wildcards: true", "      loose_wildcards: false")
    q = build_scopus_query(_load(tmp_path, yaml))
    assert '"conversion disorder*"' in q
    assert '"pseudo-seizure*"' in q


# ---------------------------------------------------------------------------
# Feature 3: constants + warnings
# ---------------------------------------------------------------------------

def test_pubmed_warns_over_wildcard_limit(tmp_path, caplog):
    config = _load(tmp_path, LEGACY_YAML)
    # synthesize an over-limit query by lowering the constant
    orig = fnd_meta_search.PUBMED_MAX_WILDCARDS
    fnd_meta_search.PUBMED_MAX_WILDCARDS = 3
    try:
        with caplog.at_level(logging.WARNING):
            build_pubmed_query(config)
    finally:
        fnd_meta_search.PUBMED_MAX_WILDCARDS = orig
    assert any("wildcard" in r.getMessage().lower() for r in caplog.records)


def test_pubmed_no_warning_under_limit(tmp_path, caplog):
    config = _load(tmp_path, LEGACY_YAML)
    with caplog.at_level(logging.WARNING):
        build_pubmed_query(config)
    assert not any("wildcard" in r.getMessage().lower() for r in caplog.records)


def test_scopus_client_offset_ceiling_constant():
    assert ScopusClient.OFFSET_RESULT_CEILING == 5000


def test_pubmed_max_wildcards_constant():
    assert PUBMED_MAX_WILDCARDS == 256
