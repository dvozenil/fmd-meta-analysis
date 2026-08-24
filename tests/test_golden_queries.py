"""Golden-query regression tests for issue #8's YAML search-config refactor.

This module is the **safety net** for the issue #8 refactoring. Before the
refactor, the full term lists and target-date options for every search mode
lived directly inside ``fnd_meta_search.py``. T2 externalized those term sets
to ``search_configs/<mode>.yaml`` and rewired ``load_search_config()`` +
the ``build_*_query()`` builders to consume a ``SearchConfig``.

The golden reference files under ``tests/golden/<mode>/`` were generated from
the *pre-refactor* code by T1 and are frozen as the byte-identical contract.
If this file ever fails, the refactor has changed query output — the golden
files are NOT to be edited to make a test pass.

Each test loads a mode's YAML config, rebuilds all five database query
strings, and asserts they match the golden reference byte-for-byte.
"""

import json

import pytest
from pathlib import Path

from fnd_meta_search import (
    build_ebsco_psycinfo_query,
    build_europepmc_query,
    build_pubmed_query,
    build_scopus_query,
    build_wos_query,
    load_search_config,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
# Repo root is one level above tests/ — where search_configs/ lives.
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "search_configs"

MODES = ["update", "full", "os_validation", "os_table_recall", "ludwig_validation"]
DBS = ["pubmed", "europepmc", "wos", "scopus", "ebsco_psycinfo"]

BUILDERS = {
    "pubmed": build_pubmed_query,
    "europepmc": build_europepmc_query,
    "wos": build_wos_query,
    "scopus": build_scopus_query,
    "ebsco_psycinfo": build_ebsco_psycinfo_query,
}


def _load_golden(mode: str) -> dict:
    golden_path = GOLDEN_DIR / mode / "queries.json"
    with open(golden_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("db", DBS)
def test_golden_queries_match(mode, db):
    """Assert a mode's YAML rebuilds a DB query byte-identical to its golden.

    Safety net for issue #8's refactoring: externalizing the term sets to
    YAML must not have changed any query output.

    ``update``/``full`` configs use the dynamic end date ``"today"``, so we
    pin the date to the golden reference's recorded ``_search_end_date`` to
    keep the test deterministic on any day the suite runs.
    """
    golden = _load_golden(mode)
    config = load_search_config(
        CONFIG_DIR / f"{mode}.yaml",
        date_end_override=golden["_search_end_date"],
    )
    query = BUILDERS[db](config)
    assert query == golden[db], f"Query mismatch for mode={mode!r}, db={db!r}"


def test_all_five_databases_present_in_every_golden():
    """Golden files must carry all 5 database queries (metadata keys prefixed _)."""
    for mode in MODES:
        golden = _load_golden(mode)
        for db in DBS:
            assert db in golden, f"golden/{mode}/queries.json missing db {db!r}"
            assert isinstance(golden[db], str) and golden[db], (
                f"golden/{mode}/queries.json has empty/non-str query for {db!r}"
            )
