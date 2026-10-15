"""Tests for search.syntax.exclude_scope and EPMC wildcard rendering.

Feature 1 — ``exclude_scope`` (``default`` | ``title``, default ``default``):
renders the ``blocks.exclude`` NOT clause title-only in all five builders
(PubMed ``[ti]``, EPMC ``TITLE:``, Scopus ``TITLE()``, EBSCO ``TI ()``,
WoS ``TI=``) instead of the DB's default search fields. Backward compatible:
unset knob = existing byte-identical output (guarded by the golden suite).

Feature 2 — Europe PMC wildcard handling: terms containing ``*`` render
UNQUOTED (Lucene bare terms — quoted wildcards return 0 hits, verified
2026-10-15); terms without ``*`` stay quoted. Applies to all EPMC blocks
(block_a/b/c and the exclude block) only; other builders untouched.
"""

import pytest
from pathlib import Path

from fnd_meta_search import (
    SearchConfig,
    build_pubmed_query,
    build_wos_query,
    build_europepmc_query,
    build_scopus_query,
    build_ebsco_psycinfo_query,
    load_search_config,
)

FIXTURE_YAML = """\
term_sets:
  fnd_terms:
    - "functional neurological disorder*"
  imaging_terms:
    - "neuroimaging"
  exclude_terms:
    - "review"
    - "meta-analysis"
    - "case report"

blocks:
  block_a: "fnd_terms"
  block_b: "imaging_terms"
  exclude: "exclude_terms"
"""

TITLE_SCOPE_YAML = FIXTURE_YAML.replace(
    'blocks:\n',
    'search:\n  syntax:\n    exclude_scope: "title"\n\nblocks:\n',
)

FIXED_DATE = "2026-08-26"


def _load(tmp_path, text, name="fixture.yaml"):
    cfg_path = tmp_path / name
    cfg_path.write_text(text, encoding="utf-8")
    return load_search_config(cfg_path, date_end_override=FIXED_DATE)


@pytest.fixture
def default_scope_config(tmp_path):
    return _load(tmp_path, FIXTURE_YAML)


@pytest.fixture
def title_scope_config(tmp_path):
    return _load(tmp_path, TITLE_SCOPE_YAML)


# ---------------------------------------------------------------------------
# Feature 1: knob parsing / validation
# ---------------------------------------------------------------------------

def test_exclude_scope_defaults_to_default(tmp_path):
    config = _load(tmp_path, FIXTURE_YAML)
    assert config.exclude_scope == "default"


def test_exclude_scope_title_parsed(tmp_path):
    config = _load(tmp_path, TITLE_SCOPE_YAML)
    assert config.exclude_scope == "title"


def test_exclude_scope_case_insensitive(tmp_path):
    config = _load(tmp_path, FIXTURE_YAML.replace(
        'blocks:\n', 'search:\n  syntax:\n    exclude_scope: "TITLE"\n\nblocks:\n'))
    assert config.exclude_scope == "title"


def test_exclude_scope_invalid_raises(tmp_path):
    with pytest.raises(ValueError, match="exclude_scope"):
        _load(tmp_path, FIXTURE_YAML.replace(
            'blocks:\n',
            'search:\n  syntax:\n    exclude_scope: "abstract"\n\nblocks:\n'))


# ---------------------------------------------------------------------------
# Feature 1: per-database title-scope NOT syntax (joining conventions kept:
# PubMed/EPMC bare NOT; Scopus/EBSCO/WoS AND NOT)
# ---------------------------------------------------------------------------

def test_pubmed_exclude_scope_title(title_scope_config):
    q = build_pubmed_query(title_scope_config)
    assert 'NOT ("review"[ti] OR "meta-analysis"[ti] OR "case report"[ti])' in q
    assert 'NOT ("review"[tiab]' not in q


def test_pubmed_default_scope_stays_tiab(default_scope_config):
    q = build_pubmed_query(default_scope_config)
    assert 'NOT ("review"[tiab] OR "meta-analysis"[tiab] OR "case report"[tiab])' in q


def test_wos_exclude_scope_title(title_scope_config):
    q = build_wos_query(title_scope_config)
    assert 'AND NOT TI=("review" OR "meta-analysis" OR "case report")' in q
    assert "AND NOT TS=(" not in q


def test_wos_default_scope_stays_ts(default_scope_config):
    q = build_wos_query(default_scope_config)
    assert 'AND NOT TS=("review" OR "meta-analysis" OR "case report")' in q


def test_europepmc_exclude_scope_title(title_scope_config):
    q = build_europepmc_query(title_scope_config)
    assert 'NOT (TITLE:("review" OR "meta-analysis" OR "case report"))' in q
    assert "TITLE_ABS:(\"review\"" not in q


def test_europepmc_default_scope_stays_title_abs(default_scope_config):
    q = build_europepmc_query(default_scope_config)
    assert 'NOT (TITLE_ABS:("review" OR "meta-analysis" OR "case report"))' in q


def test_scopus_exclude_scope_title(title_scope_config):
    q = build_scopus_query(title_scope_config)
    assert 'AND NOT TITLE("review" OR "meta-analysis" OR "case report")' in q
    assert "AND NOT TITLE-ABS-KEY(" not in q


def test_scopus_default_scope_stays_title_abs_key(default_scope_config):
    q = build_scopus_query(default_scope_config)
    assert ('AND NOT TITLE-ABS-KEY("review" OR "meta-analysis" OR "case report")'
            in q)


def test_ebsco_exclude_scope_title(title_scope_config):
    q = build_ebsco_psycinfo_query(title_scope_config)
    assert 'AND NOT TI ("review" OR "meta-analysis" OR "case report")' in q
    assert "AB (\"review\"" not in q


def test_ebsco_default_scope_stays_tiabsu(default_scope_config):
    q = build_ebsco_psycinfo_query(default_scope_config)
    phrase_or = '"review" OR "meta-analysis" OR "case report"'
    assert f'AND NOT (TI ({phrase_or}) OR AB ({phrase_or}) OR SU ({phrase_or}))' in q


def test_title_scope_positive_blocks_unchanged(title_scope_config, default_scope_config):
    """exclude_scope touches ONLY the NOT clause — positive blocks identical."""
    for builder in (build_pubmed_query, build_wos_query, build_europepmc_query,
                    build_scopus_query, build_ebsco_psycinfo_query):
        t_q = builder(title_scope_config)
        d_q = builder(default_scope_config)
        # strip the exclude clause from each and compare the positives
        assert t_q.split(" NOT ")[0].split(" AND NOT ")[0] == \
               d_q.split(" NOT ")[0].split(" AND NOT ")[0]


# ---------------------------------------------------------------------------
# Feature 2: EPMC wildcard rendering (mixed quoted/unquoted)
# ---------------------------------------------------------------------------

WILDCARD_YAML = """\
term_sets:
  a_terms:
    - "childhood maltreat*"
    - "conversion disorder"
  b_terms:
    - "neuroimaging"
    - "brain imaging"
  excl_terms:
    - "review*"
    - "meta-analysis"

blocks:
  block_a: "a_terms"
  block_b: "b_terms"
  exclude: "excl_terms"
"""


@pytest.fixture
def wildcard_config(tmp_path):
    return _load(tmp_path, WILDCARD_YAML)


def test_epmc_wildcard_terms_unquoted(wildcard_config):
    q = build_europepmc_query(wildcard_config)
    # wildcard terms: bare (no surrounding quotes)
    assert "TITLE_ABS:(childhood maltreat* OR \"conversion disorder\")" in q
    # non-wildcard terms still quoted
    assert '"neuroimaging" OR "brain imaging"' in q


def test_epmc_wildcard_in_exclude_block(wildcard_config):
    q = build_europepmc_query(wildcard_config)
    assert 'NOT (TITLE_ABS:(review* OR "meta-analysis"))' in q


def test_epmc_wildcard_title_scoped_exclude(wildcard_config):
    wildcard_config.exclude_scope = "title"
    q = build_europepmc_query(wildcard_config)
    assert 'NOT (TITLE:(review* OR "meta-analysis"))' in q


def test_epmc_wildcard_three_block(tmp_path):
    cfg = _load(tmp_path, WILDCARD_YAML.replace(
        "blocks:\n  block_a:",
        "blocks:\n  block_c: \"excl_terms\"\n  block_a:"))
    cfg.exclude = None  # focus on positive 3-block rendering
    q = build_europepmc_query(cfg)
    assert "AND (TITLE_ABS:(review* OR \"meta-analysis\"))" in q


def test_wildcard_quoting_only_changes_epmc(wildcard_config):
    """PubMed/WoS/Scopus/EBSCO keep quoting wildcard terms verbatim."""
    for builder, needle in (
        (build_pubmed_query, '"childhood maltreat*"[tiab]'),
        (build_wos_query, 'TS=("childhood maltreat*" OR "conversion disorder")'),
        (build_scopus_query, 'TITLE-ABS-KEY("childhood maltreat*" OR "conversion disorder")'),
        (build_ebsco_psycinfo_query, 'TI ("childhood maltreat*" OR "conversion disorder")'),
    ):
        assert needle in builder(wildcard_config), builder.__name__


def test_epmc_mixed_wildcard_and_plain_in_positive_block(default_scope_config):
    """Fixture block_a has one wildcard term: it renders bare, block_b stays quoted."""
    q = build_europepmc_query(default_scope_config)
    assert 'TITLE_ABS:(functional neurological disorder*)' in q
    assert 'TITLE_ABS:("neuroimaging")' in q
    # exclude block has no wildcards => fully quoted (legacy behaviour)
    assert 'NOT (TITLE_ABS:("review" OR "meta-analysis" OR "case report"))' in q


# ---------------------------------------------------------------------------
# SearchConfig direct-construction default (legacy callers unaffected)
# ---------------------------------------------------------------------------

def test_searchconfig_exclude_scope_field_default():
    cfg = SearchConfig(block_a=["x"], block_b=["y"], exclude=["z"])
    assert cfg.exclude_scope == "default"
    q = build_pubmed_query(cfg)
    assert 'NOT ("z"[tiab])' in q
