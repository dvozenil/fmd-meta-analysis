"""Tests for YAML exclusion-block (NOT) support — follow-up to issue #8.

The optional ``exclude`` block in ``blocks:`` is resolved via
``_term_set_lookup`` like ``block_c`` and appended AFTER all AND blocks in
each database's query as a per-database NOT clause.

Also asserts byte-identity of queries that do NOT use an ``exclude`` block,
guarding against accidental changes to the golden-query contract.
"""

import json

import pytest
from pathlib import Path

from fnd_meta_search import (
    load_search_config,
    build_pubmed_query,
    build_wos_query,
    build_europepmc_query,
    build_scopus_query,
    build_ebsco_psycinfo_query,
    SearchConfig,
)

# ---------------------------------------------------------------------------
# Fixture config with an exclude block
# ---------------------------------------------------------------------------

FIXTURE_YAML = """\
term_sets:
  fnd_terms:
    - "functional neurological disorder*"
    - "conversion disorder*"
  imaging_terms:
    - "neuroimaging"
    - "brain imaging"
  exclude_terms:
    - "functional MRI"
    - "fMRI"
    - "Huntington disease"

blocks:
  block_a: "fnd_terms"
  block_b: "imaging_terms"
  block_c: null
  exclude: "exclude_terms"
"""

FIXED_DATE = "2026/08/26"


@pytest.fixture
def exclude_config(tmp_path):
    """Write fixture YAML to tmp_path and load it as a SearchConfig."""
    cfg_path = tmp_path / "exclude_fixture.yaml"
    cfg_path.write_text(FIXTURE_YAML, encoding="utf-8")
    return load_search_config(cfg_path, date_end_override=FIXED_DATE)


# ---------------------------------------------------------------------------
# Per-database exclude syntax assertions
# ---------------------------------------------------------------------------

def test_pubmed_exclude_syntax(exclude_config):
    q = build_pubmed_query(exclude_config)
    # Non-MeSH branch: TEXT-block NOT syntax with [tiab] per term
    assert 'NOT ("functional MRI"[tiab] OR "fMRI"[tiab] OR "Huntington disease"[tiab])' in q


def test_wos_exclude_syntax(exclude_config):
    q = build_wos_query(exclude_config)
    # WoS: AND NOT TS=(... OR ...)
    assert 'AND NOT TS=("functional MRI" OR "fMRI" OR "Huntington disease")' in q


def test_europepmc_exclude_syntax(exclude_config):
    q = build_europepmc_query(exclude_config)
    # EuropePMC: NOT (TITLE_ABS:(... OR ...))
    assert 'NOT (TITLE_ABS:("functional MRI" OR "fMRI" OR "Huntington disease"))' in q


def test_scopus_exclude_syntax(exclude_config):
    q = build_scopus_query(exclude_config)
    # Scopus: AND NOT TITLE-ABS-KEY(... OR ...)
    assert 'AND NOT TITLE-ABS-KEY("functional MRI" OR "fMRI" OR "Huntington disease")' in q


def test_ebsco_exclude_syntax(exclude_config):
    q = build_ebsco_psycinfo_query(exclude_config)
    # EBSCO: AND NOT (TI (...) OR AB (...) OR SU (...))
    phrase_or = '"functional MRI" OR "fMRI" OR "Huntington disease"'
    assert f'AND NOT (TI ({phrase_or}) OR AB ({phrase_or}) OR SU ({phrase_or}))' in q


# ---------------------------------------------------------------------------
# Golden byte-identity assertions (no exclude block set)
# ---------------------------------------------------------------------------

GOLDEN_DIR = Path(__file__).parent / "golden"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "search_configs"


@pytest.mark.parametrize("mode", ["update", "full"])
@pytest.mark.parametrize("db", [
    ("pubmed", build_pubmed_query),
    ("wos", build_wos_query),
    ("europepmc", build_europepmc_query),
    ("scopus", build_scopus_query),
    ("ebsco_psycinfo", build_ebsco_psycinfo_query),
])
def test_golden_byte_identity_without_exclude(mode, db):
    """Modes with no exclude block must still match golden queries byte-for-byte."""
    db_name, builder = db
    golden_path = GOLDEN_DIR / mode / "queries.json"
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)
    config = load_search_config(
        CONFIG_DIR / f"{mode}.yaml",
        date_end_override=golden["_search_end_date"],
    )
    query = builder(config)
    assert query == golden[db_name], (
        f"Query mismatch for mode={mode!r}, db={db_name!r} — "
        f"byte-identity gate failed"
    )
