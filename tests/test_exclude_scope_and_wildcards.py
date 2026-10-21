"""Tests for search.syntax.exclude_scope and EPMC wildcard rendering.

Feature 1 — ``exclude_scope`` (``default`` | ``title``, default ``default``):
renders the ``blocks.exclude`` NOT clause title-only in all five builders
(PubMed ``[ti]``, EPMC ``TITLE:``, Scopus ``TITLE()``, EBSCO ``TI ()``,
WoS ``TI=``) instead of the DB's default search fields. Backward compatible:
unset knob = existing byte-identical output (guarded by the golden suite).

The knob is EXCLUSION-ONLY by design (WoS-mirroring semantics: TI-scoped
exclusions + TS-scoped topic search). Positive/inclusion blocks keep their
per-builder default field scope (EPMC TITLE_ABS, PubMed [tiab], WoS TS=,
Scopus TITLE-ABS-KEY, EBSCO TI/AB/SU) and must NEVER be title-scoped. The
``scope lock`` tests below pin that asymmetry for all five builders.

Feature 2 — Europe PMC wildcard handling: terms containing ``*`` render
UNQUOTED and individually parenthesized — ``(functional motor disorder*) OR
(functional tremor*)``. Two independent reasons:
  (a) EPMC does not stem-expand a wildcard inside quotes; quoted wildcards
      are matched near-literally, with term-dependent results — some return
      0 hits (``TITLE_ABS:"childhood maltreat*"`` = 0 vs 15,714 unquoted),
      others still match a handful (``TITLE_ABS:"functional/dissociative
      seizure*"`` = 8 vs 203 unquoted). Verified 2026-10-15.
  (b) Unparenthesized multiword bare terms chained with OR inside a field
      group are parsed by Lucene as cross-term implicit ANDs, so the block
      collapses toward 0 hits (10-term group = 174 hits vs 49,047 for the
      per-term-parenthesized form, verified live 2026-10-15).
Quoted non-wildcard terms keep their current form. Applies to all EPMC
blocks (block_a/b/c and the exclude block) only; other builders untouched.
"""

import pytest
from pathlib import Path

import urllib.parse

import fnd_meta_search
import requests as fms_requests
from fnd_meta_search import (
    EuropePMCClient,
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
    """exclude_scope touches ONLY the NOT clause — positive blocks identical.

    Coarse prefix comparison (kept alongside the explicit per-builder scope
    locks below, which use wildcard-bearing inclusion blocks).
    """
    for builder in (build_pubmed_query, build_wos_query, build_europepmc_query,
                    build_scopus_query, build_ebsco_psycinfo_query):
        t_q = builder(title_scope_config)
        d_q = builder(default_scope_config)
        # strip the exclude clause from each and compare the positives
        assert t_q.split(" NOT ")[0].split(" AND NOT ")[0] == \
               d_q.split(" NOT ")[0].split(" AND NOT ")[0]


# ---------------------------------------------------------------------------
# Feature 1 (C1): exclusion-only asymmetry is DELIBERATE and pinned.
#
# With exclude_scope="title" ONLY the NOT clause may move to the title field;
# every positive/inclusion block keeps its per-builder default field scope
# (WoS-mirroring semantics: TI-scoped exclusions + TS-scoped topic search).
# These are "scope lock" tests: a refactor that title-scopes the positive
# blocks (the exact issue the adversarial review flagged) must fail here.
# ---------------------------------------------------------------------------

SCOPE_LOCK_YAML = """\
term_sets:
  a_terms:
    - "functional motor disorder*"
    - "functional tremor*"
  b_terms:
    - "neuroimaging"
    - "brain imaging*"
  excl_terms:
    - "review"
    - "meta-analysis"
    - "case report"

blocks:
  block_a: "a_terms"
  block_b: "b_terms"
  exclude: "excl_terms"
"""

SCOPE_LOCK_TITLE_YAML = SCOPE_LOCK_YAML.replace(
    'blocks:\n',
    'search:\n  syntax:\n    exclude_scope: "title"\n\nblocks:\n',
)


@pytest.fixture
def scope_lock_default(tmp_path):
    return _load(tmp_path, SCOPE_LOCK_YAML, name="scope_lock_default.yaml")


@pytest.fixture
def scope_lock_title(tmp_path):
    return _load(tmp_path, SCOPE_LOCK_TITLE_YAML, name="scope_lock_title.yaml")


SCOPE_LOCK_CASES = [
    pytest.param(
        build_pubmed_query,
        [
            '"functional motor disorder*"[tiab]',
            '"functional tremor*"[tiab]',
            '"neuroimaging"[tiab]',
            '"brain imaging*"[tiab]',
            '"Conversion Disorder"[MeSH]',
        ],
        'NOT ("review"[tiab] OR "meta-analysis"[tiab] OR "case report"[tiab])',
        'NOT ("review"[ti] OR "meta-analysis"[ti] OR "case report"[ti])',
        id="pubmed",
    ),
    pytest.param(
        build_europepmc_query,
        [
            'TITLE_ABS:((functional motor disorder*) OR (functional tremor*))',
            'TITLE_ABS:("neuroimaging" OR (brain imaging*))',
        ],
        'NOT (TITLE_ABS:("review" OR "meta-analysis" OR "case report"))',
        'NOT (TITLE:("review" OR "meta-analysis" OR "case report"))',
        id="europepmc",
    ),
    pytest.param(
        build_wos_query,
        [
            'TS=("functional motor disorder*" OR "functional tremor*")',
            'TS=("neuroimaging" OR "brain imaging*")',
        ],
        'AND NOT TS=("review" OR "meta-analysis" OR "case report")',
        'AND NOT TI=("review" OR "meta-analysis" OR "case report")',
        id="wos",
    ),
    pytest.param(
        build_scopus_query,
        [
            'TITLE-ABS-KEY("functional motor disorder*" OR "functional tremor*")',
            'TITLE-ABS-KEY("neuroimaging" OR "brain imaging*")',
        ],
        'AND NOT TITLE-ABS-KEY("review" OR "meta-analysis" OR "case report")',
        'AND NOT TITLE("review" OR "meta-analysis" OR "case report")',
        id="scopus",
    ),
    pytest.param(
        build_ebsco_psycinfo_query,
        [
            'TI ("functional motor disorder*" OR "functional tremor*")',
            'AB ("neuroimaging" OR "brain imaging*")',
            'SU ("neuroimaging" OR "brain imaging*")',
        ],
        ('AND NOT (TI ("review" OR "meta-analysis" OR "case report") '
         'OR AB ("review" OR "meta-analysis" OR "case report") '
         'OR SU ("review" OR "meta-analysis" OR "case report"))'),
        'AND NOT TI ("review" OR "meta-analysis" OR "case report")',
        id="ebsco_psycinfo",
    ),
]


@pytest.mark.parametrize("builder, include_markers, default_excl, title_excl",
                         SCOPE_LOCK_CASES)
def test_title_scope_changes_only_the_exclusion_clause(
        builder, include_markers, default_excl, title_excl,
        scope_lock_default, scope_lock_title):
    """exclude_scope=title must be a pure exclusion-clause substitution.

    Strong form: the title-scoped query must equal the default query with
    exactly the exclusion text swapped. Any change to a positive block — or
    to joining conventions / language & date suffix placement — breaks
    equality, so a silent title-scoping refactor cannot pass.
    """
    default_q = builder(scope_lock_default)
    title_q = builder(scope_lock_title)
    for marker in include_markers:
        assert marker in default_q, f"fixture marker missing (default): {marker}"
        assert marker in title_q, (
            f"positive block changed scope under exclude_scope=title: {marker}"
        )
    assert default_excl in default_q
    assert title_excl in title_q
    assert title_q == default_q.replace(default_excl, title_excl)


def test_pubmed_title_scope_leaves_only_ti_in_exclusion(scope_lock_title):
    q = build_pubmed_query(scope_lock_title)
    # [ti] appears only in the three exclusion terms; inclusions stay [tiab].
    assert q.count("[ti]") == 3
    assert '"brain imaging*"[tiab]' in q


def test_europepmc_title_scope_keeps_title_abs_inclusions(scope_lock_title):
    q = build_europepmc_query(scope_lock_title)
    assert q.count("TITLE_ABS:(") == 2   # block_a + block_b
    assert q.count("TITLE:(") == 1       # exclusion only


def test_wos_title_scope_keeps_ts_inclusions(scope_lock_title):
    q = build_wos_query(scope_lock_title)
    assert q.count("TS=(") == 2          # block_a + block_b
    assert q.count("TI=(") == 1          # exclusion only


def test_scopus_title_scope_keeps_title_abs_key_inclusions(scope_lock_title):
    q = build_scopus_query(scope_lock_title)
    assert q.count("TITLE-ABS-KEY(") == 2
    assert q.count("TITLE(") == 1        # exclusion only


def test_ebsco_title_scope_keeps_ti_ab_su_inclusions(scope_lock_title):
    q = build_ebsco_psycinfo_query(scope_lock_title)
    assert q.count("TI (") == 3          # 2 inclusion blocks + 1 exclusion
    assert q.count("AB (") == 2
    assert q.count("SU (") == 2


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
    # wildcard terms: bare AND individually parenthesized
    assert 'TITLE_ABS:((childhood maltreat*) OR "conversion disorder")' in q
    # non-wildcard terms still quoted
    assert '"neuroimaging" OR "brain imaging"' in q


def test_epmc_wildcard_in_exclude_block(wildcard_config):
    q = build_europepmc_query(wildcard_config)
    assert 'NOT (TITLE_ABS:((review*) OR "meta-analysis"))' in q


def test_epmc_wildcard_title_scoped_exclude(wildcard_config):
    wildcard_config.exclude_scope = "title"
    q = build_europepmc_query(wildcard_config)
    assert 'NOT (TITLE:((review*) OR "meta-analysis"))' in q


def test_epmc_wildcard_three_block(tmp_path):
    cfg = _load(tmp_path, WILDCARD_YAML.replace(
        "blocks:\n  block_a:",
        "blocks:\n  block_c: \"excl_terms\"\n  block_a:"))
    cfg.exclude = None  # focus on positive 3-block rendering
    q = build_europepmc_query(cfg)
    assert "AND (TITLE_ABS:((review*) OR \"meta-analysis\"))" in q


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
    """Fixture block_a has one wildcard term: it renders bare+parenthesized."""
    q = build_europepmc_query(default_scope_config)
    assert 'TITLE_ABS:((functional neurological disorder*))' in q
    assert 'TITLE_ABS:("neuroimaging")' in q
    # exclude block has no wildcards => fully quoted (legacy behaviour)
    assert 'NOT (TITLE_ABS:("review" OR "meta-analysis" OR "case report"))' in q


# ---------------------------------------------------------------------------
# Feature 2 (C2): EVERY unquoted wildcard term is individually parenthesized,
# in all four EPMC block positions (block_a, block_b, block_c, exclude path).
#
# Locked because the previous render — ``TITLE_ABS:(functional motor
# disorder* OR functional tremor* OR ...)`` — is parsed by Lucene as
# cross-term implicit ANDs and collapses toward 0 hits (the committed
# full/update golden queries returned 0 live hits before this fix).
# ---------------------------------------------------------------------------

MULTI_WILDCARD_YAML = """\
term_sets:
  a_terms:
    - "functional motor disorder*"
    - "functional tremor*"
    - "conversion disorder"
  b_terms:
    - "neuroimaging*"
    - "brain imaging"
  c_terms:
    - "case-control*"
    - "cohort*"
  excl_terms:
    - "review*"
    - "case report*"
    - "meta-analysis"

blocks:
  block_a: "a_terms"
  block_b: "b_terms"
  block_c: "c_terms"
  exclude: "excl_terms"
"""


@pytest.fixture
def multi_wildcard_config(tmp_path):
    return _load(tmp_path, MULTI_WILDCARD_YAML, name="multi_wildcard.yaml")


def test_epmc_helper_parenthesizes_each_wildcard_term():
    from fnd_meta_search import _build_europepmc_phrase_or_block
    assert _build_europepmc_phrase_or_block(
        ["functional motor disorder*", "functional tremor*", "conversion disorder"]
    ) == ('(functional motor disorder*) OR (functional tremor*) '
          'OR "conversion disorder"')


def test_epmc_helper_parenthesizes_single_wildcard_term():
    from fnd_meta_search import _build_europepmc_phrase_or_block
    assert _build_europepmc_phrase_or_block(["review*"]) == "(review*)"


def test_epmc_helper_leaves_plain_terms_quoted():
    from fnd_meta_search import _build_europepmc_phrase_or_block
    assert _build_europepmc_phrase_or_block(
        ["conversion disorder", "meta-analysis"]
    ) == '"conversion disorder" OR "meta-analysis"'


def test_epmc_inclusion_block_a_each_wildcard_parenthesized(multi_wildcard_config):
    q = build_europepmc_query(multi_wildcard_config)
    assert ('TITLE_ABS:((functional motor disorder*) OR (functional tremor*) '
            'OR "conversion disorder")') in q


def test_epmc_inclusion_block_b_wildcard_parenthesized(multi_wildcard_config):
    q = build_europepmc_query(multi_wildcard_config)
    assert 'TITLE_ABS:((neuroimaging*) OR "brain imaging")' in q


def test_epmc_block_c_wildcards_parenthesized(multi_wildcard_config):
    q = build_europepmc_query(multi_wildcard_config)
    assert 'AND (TITLE_ABS:((case-control*) OR (cohort*)))' in q


def test_epmc_exclude_block_wildcards_parenthesized(multi_wildcard_config):
    q = build_europepmc_query(multi_wildcard_config)
    assert 'NOT (TITLE_ABS:((review*) OR (case report*) OR "meta-analysis"))' in q


def test_epmc_exclude_block_wildcards_parenthesized_title_scope(
        multi_wildcard_config):
    multi_wildcard_config.exclude_scope = "title"
    q = build_europepmc_query(multi_wildcard_config)
    assert 'NOT (TITLE:((review*) OR (case report*) OR "meta-analysis"))' in q
    # same config: inclusion blocks must stay TITLE_ABS (C1 asymmetry)
    assert ('TITLE_ABS:((functional motor disorder*) OR (functional tremor*) '
            'OR "conversion disorder")') in q
    assert 'TITLE_ABS:((case-control*) OR (cohort*))' in q


def test_epmc_multi_wildcard_full_query_golden(multi_wildcard_config):
    """Byte-golden for the complete rendered EPMC query (all four blocks)."""
    assert build_europepmc_query(multi_wildcard_config) == (
        '(TITLE_ABS:((functional motor disorder*) OR (functional tremor*) '
        'OR "conversion disorder")) AND (TITLE_ABS:((neuroimaging*) OR '
        '"brain imaging")) AND (TITLE_ABS:((case-control*) OR (cohort*))) '
        'NOT (TITLE_ABS:((review*) OR (case report*) OR "meta-analysis")) '
        'AND (LANG:"eng") AND (PUB_YEAR:[1800 TO 2026])'
    )


def test_epmc_multi_wildcard_query_parentheses_balanced(multi_wildcard_config):
    q = build_europepmc_query(multi_wildcard_config)
    assert q.count("(") == q.count(")")


# ---------------------------------------------------------------------------
# SearchConfig direct-construction default (legacy callers unaffected)
# ---------------------------------------------------------------------------

def test_searchconfig_exclude_scope_field_default():
    cfg = SearchConfig(block_a=["x"], block_b=["y"], exclude=["z"])
    assert cfg.exclude_scope == "default"
    q = build_pubmed_query(cfg)
    assert 'NOT ("z"[tiab])' in q


# ---------------------------------------------------------------------------
# EPMC GET request-line length: parentheses must NOT be percent-encoded
# (verified live 2026-10-19: default encoding pushed Martin's v2 draft query
# to ~7.9k encoded bytes -> bare HTTP 400; parens-raw form = 3,017 hits)
# ---------------------------------------------------------------------------

def test_epmc_encode_param_keeps_parens_raw():
    enc = EuropePMCClient._encode_param
    # parens and asterisks stay raw; quotes must remain percent-encoded.
    # '/' and ':' encode to %2F/%3A — harmless (servlets decode them), only
    # parens/quotes/spaces affect the request-line budget.
    assert enc("(functional tremor*)") == "(functional+tremor*)"
    assert enc('"ME/CFS"') == "%22ME%2FCFS%22"
    assert enc("a b") == "a+b"


def test_epmc_encode_param_saves_request_line_length():
    # the whole multi-wildcard exposure block must encode shorter than with
    # parens percent-encoded — that delta is what crosses the ~8KB ceiling
    block = " OR ".join(f"(functional motor disorder*)" for _ in range(100))
    default_len = len(urllib.parse.urlencode({"q": block}))
    ours_len = len("q=" + EuropePMCClient._encode_param(block))
    assert ours_len < default_len - 300  # ~2 bytes saved per paren


def test_epmc_client_builds_unencoded_paren_url(monkeypatch):
    # capture the URL the client actually GETs; assert parens arrive raw
    captured = {}
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"resultList": {"result": []}}
    def fake_get(url, timeout=None, **kw):
        captured["url"] = url
        return FakeResp()
    monkeypatch.setattr(fms_requests, "get", fake_get)
    cfg = SearchConfig(
        block_a=["functional motor disorder*", "functional tremor*"],
        block_b=["child*"],
        date_start=None, date_end="2026/12/31",
    )
    EuropePMCClient().search(build_europepmc_query(cfg), page_size=1)
    url = captured["url"]
    assert "TITLE_ABS%3A%28" not in url        # parens NOT percent-encoded
    assert "TITLE_ABS%3A((functional" in url   # they arrive raw (colon is %3A, harmless)
