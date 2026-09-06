"""Integration tests for the --db CLI flag (issue #8).

``--db NAME`` restricts which API clients *execute* during a search run, but
all five query strings are still generated for ``queries.json``/``queries.txt``
(the EBSCO PsycInfo query is always produced because it is executed manually
on EBSCOhost).

Two layers are exercised here:

1. **Argument parsing** — ``_parse_args()`` turns repeated ``--db`` flags into
   the correct client subset and rejects unknown database names.
2. **run_searches() filtering** — with API clients mocked out, only the
   requested clients call ``search()``, yet all five queries are still built.
"""

import sys

import pytest
from unittest import mock

import fnd_meta_search as fms

ALL_DBS = ["pubmed", "europepmc", "wos", "scopus", "ebsco_psycinfo"]
# CLI-executable clients (EBSCO PsycInfo is manual-only).
API_DBS = ["pubmed", "europepmc", "wos", "scopus"]


# ---------------------------------------------------------------------------
# Layer 1: --db argument parsing
# ---------------------------------------------------------------------------

def test_parse_args_accumulates_db_subset(monkeypatch):
    """Repeated --db flags accumulate into the exact client subset."""
    monkeypatch.setattr(sys, "argv", ["fnd_meta_search", "--db", "pubmed", "--db", "scopus"])
    ns = fms._parse_args()
    assert ns.db == ["pubmed", "scopus"]


def test_parse_args_db_default_none(monkeypatch):
    """Absent --db means no filter (None -> empty list at module level)."""
    monkeypatch.setattr(sys, "argv", ["fnd_meta_search", "--full"])
    ns = fms._parse_args()
    assert ns.db is None


@pytest.mark.parametrize("bad", ["bogus", "ebsco_psycinfo", "PsyCINFO"])
def test_parse_args_rejects_invalid_db(monkeypatch, bad):
    """Unknown / non-API database names are rejected by argparse."""
    monkeypatch.setattr(sys, "argv", ["fnd_meta_search", "--db", bad])
    with pytest.raises(SystemExit):
        fms._parse_args()


# ---------------------------------------------------------------------------
# Layer 2: run_searches() honours DB_FILTER but always builds all 5 queries
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_run_searches(monkeypatch, tmp_path):
    """Wire run_searches() with mocked clients and a real search config.

    Returns a namespace recording which client names had search() called and
    the (all_records, by_db, per_db, queries) tuple run_searches() returned.
    """
    executed: list[str] = []

    def make_fake(name: str):
        class _Fake:
            def search(self, query):  # noqa: D401
                executed.append(name)
                return []
        return _Fake()

    monkeypatch.setattr(fms, "PubMedClient", lambda: make_fake("pubmed"))
    monkeypatch.setattr(fms, "EuropePMCClient", lambda: make_fake("europepmc"))
    monkeypatch.setattr(fms, "WebOfScienceClient", lambda: make_fake("wos"))
    monkeypatch.setattr(fms, "ScopusClient", lambda: make_fake("scopus"))
    monkeypatch.setattr(fms, "_recover_abstracts", lambda records: None)
    monkeypatch.setattr(fms, "AUTO_MODE", False)

    cfg = fms.load_search_config(
        fms.Path(__file__).resolve().parents[1] / "search_configs" / "update.yaml"
    )
    monkeypatch.setattr(fms, "_active_search_config", lambda: cfg)
    monkeypatch.setattr(fms, "OUTPUT_DIR", tmp_path)

    return executed


@pytest.mark.parametrize("db_filter", [
    ["pubmed"],
    ["scopus", "wos"],
    ["pubmed", "europepmc", "wos", "scopus"],  # no filtering
])
def test_db_filter_limits_execution_but_builds_all_queries(mock_run_searches, monkeypatch, db_filter):
    """--db restricts which clients run; all 5 queries are still generated."""
    executed = mock_run_searches
    monkeypatch.setattr(fms, "DB_FILTER", list(db_filter))

    all_records, by_db, per_db, queries = fms.run_searches()

    assert sorted(executed) == sorted(db_filter), (
        f"expected only {sorted(db_filter)} to execute, got {sorted(executed)}"
    )
    # Every client that ran contributed to per-db counts (0 records here).
    for db in db_filter:
        assert per_db[db] == 0
    # All 5 query strings are present and non-empty regardless of --db.
    for db in ALL_DBS:
        assert db in queries, f"queries missing db {db!r}"
        assert isinstance(queries[db], str) and queries[db], f"empty query for {db!r}"
    # run_searches returned empty record sets (mocked clients); by_db holds
    # exactly the executed clients (each mapped to its empty result list).
    assert all_records == []
    assert set(by_db) == set(db_filter)
    for db in db_filter:
        assert by_db[db] == []
