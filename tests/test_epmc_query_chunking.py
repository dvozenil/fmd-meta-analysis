"""Tests for Europe PMC automatic query chunking (URL-length fallback).

Background: Europe PMC's REST GET is fronted by Tomcat, which rejects request
lines above ~8 KB with a bare HTTP 400. ``EuropePMCClient._encode_param``
keeps the line compact but cannot rescue a long rendered query — e.g. the FND
block rendered with quoted-phrase enumeration (the EPMC recall-audit
recommendation) pushes the production ``full`` query from 3,998 to 8,397
request-line bytes. ``EuropePMCClient.search`` therefore splits ONE positive
OR-group at term boundaries and unions the chunk results:

    (A1 OR ... OR An) AND B AND filters
        ==  union_i [ (A_chunk_i) AND B AND filters ]

The identity is set-theoretic, so chunking cannot change recall. These tests
run offline (``requests.get`` is replaced by a tiny EPMC stand-in) and pin:

  * **golden** — a query that fits still issues exactly one GET, with the URL
    the pre-chunking code would have built, and returns records in EPMC order;
  * the split is a **partition** — every term appears in exactly one chunk, in
    order, and every non-split clause stays byte-identical;
  * every chunk request line stays under the ceiling, with the per-chunk
    budget derived from the real encoded bytes of the remaining query rather
    than a hardcoded character count;
  * the merged result set **equals** the one-shot result set, duplicates are
    collapsed on ``(source, id)``, and the merge is logged for PRISMA-S;
  * the ``NOT`` (exclusion) clause is never split;
  * queries that cannot be made to fit raise ``QueryTooLongError`` with an
    actionable message instead of a bare HTTP 400.
"""

import logging
import re
import urllib.parse
from pathlib import Path

import pytest
import requests as fms_requests

import fnd_meta_search
from fnd_meta_search import (
    EPMCChunkPlan,
    EuropePMCClient,
    QueryTooLongError,
    SearchConfig,
    _find_or_terms,
    _split_conjuncts,
    build_europepmc_query,
    load_search_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _fake_hit(rid: str, source: str = "MED") -> dict:
    return {
        "source": source,
        "id": rid,
        "title": f"Record {rid}",
        "abstractText": f"Abstract {rid}",
        "authorString": "Doe J",
        "pubYear": "2020",
    }


class _Resp:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeEPMC:
    """Minimal stand-in for the EPMC ``/search`` endpoint.

    Answers a query with the union of the canned hits of every known term it
    contains, deduplicated on ``(source, id)`` — i.e. what EPMC does once the
    query is valid. Pagination follows ``pageSize``/``cursorMark`` so the
    client's paging loop is exercised too.

    The synthetic term matrix is built so that every A-term hit also matches
    the (empty) B-term, which makes "union over terms" a faithful model of
    "union over chunks" for these fixtures.
    """

    def __init__(self, term_hits: dict[str, list[dict]]):
        self.term_hits = term_hits
        self.urls: list[str] = []
        self.queries: list[str] = []

    def __call__(self, url, timeout=None, **kwargs):
        self.urls.append(url)
        params = urllib.parse.parse_qs(
            urllib.parse.urlsplit(url).query, keep_blank_values=True
        )
        query = params["query"][0]
        cursor = params["cursorMark"][0]
        page_size = int(params["pageSize"][0])
        self.queries.append(query)

        matched: list[dict] = []
        for term, hits in self.term_hits.items():
            if term in query:
                matched.extend(hits)
        unique: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for hit in matched:
            key = (hit.get("source"), hit.get("id"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)

        start = 0 if cursor == "*" else int(cursor)
        page = unique[start:start + page_size]
        nxt = start + page_size
        payload = {
            "hitCount": len(unique),
            "resultList": {"result": page},
        }
        if nxt < len(unique):
            payload["nextCursorMark"] = str(nxt)
        return _Resp(payload)


def _legacy_url(query: str, page_size: int, cursor: str = "*") -> str:
    """Rebuild the exact URL the pre-chunking ``search()`` produced.

    This is the golden contract for the "short query" path: same parameter
    order, same per-value encoding, same base URL.
    """
    params = {
        "query": query,
        "format": "json",
        "pageSize": page_size,
        "cursorMark": cursor,
        "resultType": "core",
    }
    qs = "&".join(
        f"{k}={EuropePMCClient._encode_param(v)}" for k, v in params.items()
    )
    return f"{EuropePMCClient.BASE}?{qs}"


def _small_config(**overrides) -> SearchConfig:
    """A compact but multi-group config for transport tests."""
    kwargs = {
        "block_a": [f"symptom{i:02d}*" for i in range(12)],
        "block_b": ["imaging*"],
        "date_start": None,
        "date_end": "2026/12/31",
        "language_filter": True,
    }
    kwargs.update(overrides)
    return SearchConfig(**kwargs)


def _term_hits_for(config: SearchConfig) -> dict[str, list[dict]]:
    """Canned per-term hits; heavy overlap so chunks return duplicates."""
    hits = [_fake_hit(f"h{i}") for i in range(8)]
    matrix: dict[str, list[dict]] = {}
    # Render exactly like the builder so substring matching works.
    block_a = fnd_meta_search._build_europepmc_phrase_or_block(config.block_a)
    terms = block_a.split(" OR ")
    for i, rendered_term in enumerate(terms):
        matrix[rendered_term] = [
            hits[i % 8], hits[(i + 1) % 8], hits[(i + 2) % 8]
        ]
    # The imaging block contributes no hits of its own: every record already
    # matches it, which keeps the fake's union model faithful to the AND.
    matrix[f"({config.block_b[0].replace('*', '')}*)"] = []
    return matrix


def _phrase_variants(term: str) -> list[str]:
    """Base phrase + naive plural, mirroring the audit prototype's enumeration."""
    base = term.replace("*", "").strip()
    words = base.split()
    variants = [base]
    if words:
        last = words[-1]
        if last.endswith(("s", "x", "z", "ch", "sh")):
            plural = last + "es"
        elif last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
            plural = last[:-1] + "ies"
        else:
            plural = last + "s"
        variants.append(" ".join(words[:-1] + [plural]))
    out: list[str] = []
    for variant in variants:
        if variant not in out:
            out.append(variant)
    return out


def _phrase_enum_block(terms: list[str]) -> str:
    rendered = [
        " OR ".join(f'"{variant}"' for variant in _phrase_variants(term))
        for term in terms
    ]
    return " OR ".join(rendered)


def _phrase_enum_query(config: SearchConfig) -> str:
    """Reproduce the audit prototype's ``build_query('phrase_enum')`` rendering.

    This is the rendering the EPMC recall audit recommends (quoted phrases
    with enumerated plurals) and the one that overflows the request line. It
    is a *transport* fixture here — production rendering is deliberately
    untouched by this change.
    """
    fnd = _phrase_enum_block(config.block_a)
    imag = _phrase_enum_block(config.block_b)
    lang = ' AND (LANG:"eng")' if config.language_filter else ""
    date = f" AND (PUB_YEAR:[{fnd_meta_search._date_filter_year_range(config)}])"
    return f"(TITLE_ABS:({fnd})) AND (TITLE_ABS:({imag})){lang}{date}"


def _fixed_remainder(query: str, plan: EPMCChunkPlan) -> str:
    """Query with the split group's text replaced by a placeholder."""
    conj = _split_conjuncts(query)
    sep, text = conj[plan.group_index]
    prefix, _terms, suffix = _find_or_terms(text)
    assert text == prefix + " OR ".join(_terms) + suffix  # decomposition is exact
    conj[plan.group_index] = (sep, "GROUP")
    return "".join(s + t for s, t in conj)


def _group_terms(query: str, plan: EPMCChunkPlan) -> tuple[str, str, list[str]]:
    conj = _split_conjuncts(query)
    _sep, text = conj[plan.group_index]
    prefix, terms, suffix = _find_or_terms(text)
    return prefix, suffix, terms


# ---------------------------------------------------------------------------
# Golden: fitting queries are untouched (byte-identical single-request path)
# ---------------------------------------------------------------------------


def test_short_query_sends_exactly_the_legacy_url(monkeypatch):
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    assert EuropePMCClient.plan_chunks(query, 1000) is None  # fits

    fake = _FakeEPMC(_term_hits_for(cfg))
    monkeypatch.setattr(fms_requests, "get", fake)

    records = EuropePMCClient().search(query, page_size=1000)

    assert fake.urls == [_legacy_url(query, 1000)]
    assert [r.source_id for r in records] == [f"h{i}" for i in range(8)]
    assert all(r.source_db == "europepmc" for r in records)


def test_production_full_query_still_fits_and_is_byte_identical(monkeypatch):
    """The production ``full`` EPMC query takes the unchanged single-request path.

    3,998 request-line bytes today — far below the ceiling — so chunking must
    be a no-op for it: one GET, legacy URL, no dedup pass.
    """
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = build_europepmc_query(cfg)
    assert EuropePMCClient._request_line_bytes(query, 1000) < 7500
    assert EuropePMCClient.plan_chunks(query, 1000) is None

    fake = _FakeEPMC({"(functional tremor*)": [_fake_hit("prod1")]})
    monkeypatch.setattr(fms_requests, "get", fake)

    records = EuropePMCClient().search(query, page_size=1000)
    assert [r.source_id for r in records] == ["prod1"]
    assert fake.urls == [_legacy_url(query, 1000)]


# ---------------------------------------------------------------------------
# Oversized query: split plan
# ---------------------------------------------------------------------------


def test_phrase_enum_query_would_exceed_the_real_ceiling():
    """Sanity-pin the fixture: this query really is over Tomcat's 8 KB limit."""
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = _phrase_enum_query(cfg)
    request_bytes = EuropePMCClient._request_line_bytes(query, 1000)
    # Tomcat's measured failure threshold is ~8 KB; the fixture must exceed it.
    assert request_bytes > 8192, request_bytes
    # And the ceiling the client enforces is conservative.
    assert request_bytes > EuropePMCClient.MAX_REQUEST_LINE_BYTES


def test_oversized_query_plans_chunks_that_all_fit():
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = _phrase_enum_query(cfg)

    plan = EuropePMCClient.plan_chunks(query, 1000)

    assert plan is not None and isinstance(plan, EPMCChunkPlan)
    assert plan.n_chunks >= 2
    assert len(plan.chunks) == len(plan.term_counts) == len(plan.encoded_sizes)
    for chunk, size in zip(plan.chunks, plan.encoded_sizes):
        assert size == EuropePMCClient._request_line_bytes(chunk, 1000)
        assert size + EuropePMCClient.CURSOR_RESERVE_BYTES <= 7500
    # every term lands in exactly one chunk
    assert sum(plan.term_counts) == len(_group_terms(query, plan)[2])


def test_chunk_budget_is_derived_from_the_actual_remaining_query():
    """A bigger non-split remainder must force more (smaller) chunks.

    This is the property that rules out a hardcoded chunk budget: with the
    same absolute request-line limit, adding unrelated clauses to the query
    shrinks the per-chunk term allowance even though the term list itself is
    unchanged.
    """
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    limit = EuropePMCClient._request_line_bytes(query, 1000) - 2 * 20

    padded_query = query + ' AND (LANG:"eng") AND (LANG:"eng") AND (LANG:"eng")'

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(EuropePMCClient, "CURSOR_RESERVE_BYTES", 0)
        mp.setattr(EuropePMCClient, "MAX_REQUEST_LINE_BYTES", limit)
        lean = EuropePMCClient.plan_chunks(query, 1000)
        padded = EuropePMCClient.plan_chunks(padded_query, 1000)

    assert lean is not None and padded is not None
    assert padded.n_chunks > lean.n_chunks
    assert all(size <= limit for size in padded.encoded_sizes)


def test_split_is_a_partition_of_the_original_terms():
    """No term dropped, duplicated, reordered or split mid-term."""
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = _phrase_enum_query(cfg)
    plan = EuropePMCClient.plan_chunks(query, 1000)
    prefix, suffix, original_terms = _group_terms(query, plan)

    recovered: list[str] = []
    for chunk in plan.chunks:
        chunk_prefix, chunk_suffix, chunk_terms = _group_terms(chunk, plan)
        assert chunk_prefix == prefix
        assert chunk_suffix == suffix
        recovered.extend(chunk_terms)

    assert recovered == original_terms  # same order, same count, same text


def test_non_split_clauses_are_byte_identical_across_chunks():
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = _phrase_enum_query(cfg)
    plan = EuropePMCClient.plan_chunks(query, 1000)

    baseline = _fixed_remainder(query, plan)
    for chunk in plan.chunks:
        assert _fixed_remainder(chunk, plan) == baseline
    # the imaging block and the filters survive verbatim
    imag = _phrase_enum_block(cfg.block_b)
    for chunk in plan.chunks:
        assert f"(TITLE_ABS:({imag}))" in chunk
        assert ' AND (LANG:"eng")' in chunk
        assert "(PUB_YEAR:[" in chunk


def test_mri_fallback_arm_is_kept_whole(monkeypatch):
    """The mri_fallback arm is an AND-expression inside the OR-list.

    Splitting must keep it as one term: breaking it apart would change
    ``("magnetic" AND "resonance" AND "imaging")`` into an OR of loose words.
    """
    arm = '("magnetic" AND "resonance" AND "imaging")'

    # (a) FND block split: the arm belongs to the untouched imaging clause and
    #     therefore appears verbatim in every chunk.
    cfg = _small_config(mri_fallback=True)
    query = build_europepmc_query(cfg)
    assert f"OR {arm}" in query
    _force_chunking(monkeypatch, query)
    plan = EuropePMCClient.plan_chunks(query, 1000)
    assert plan is not None and plan.group_index == 0
    assert all(arm in chunk for chunk in plan.chunks)

    # (b) imaging block split: the arm is now one term of the split list and
    #     must land in exactly one chunk, still intact.
    cfg = _small_config(block_b=[f"imaging{i:02d}*" for i in range(12)],
                        mri_fallback=True)
    query = build_europepmc_query(cfg)
    _force_chunking(monkeypatch, query)
    plan = EuropePMCClient.plan_chunks(query, 1000)
    assert plan is not None and plan.group_index == 1 and plan.n_chunks >= 2
    assert sum(1 for chunk in plan.chunks if arm in chunk) == 1
    for chunk in plan.chunks:  # grouping stays balanced
        assert chunk.count("(") == chunk.count(")")
        assert chunk.count('"') % 2 == 0


def test_negated_subexpression_is_never_split():
    """Disjunctions distribute over AND but not over NOT."""
    assert _find_or_terms('(TITLE_ABS:(alpha* OR beta*))') is not None
    assert _find_or_terms('(TITLE_ABS:(alpha* AND NOT (beta* OR gamma*)))') is None
    assert _find_or_terms('NOT (TITLE_ABS:(alpha* OR beta*))') is None


def test_plan_is_deterministic():
    cfg = load_search_config(REPO_ROOT / "search_configs" / "full.yaml")
    query = _phrase_enum_query(cfg)
    first = EuropePMCClient.plan_chunks(query, 1000)
    second = EuropePMCClient.plan_chunks(query, 1000)
    assert first == second


def test_three_block_query_keeps_block_c_intact():
    """ludwig_validation renders FND x stressor x design; only one block splits."""
    cfg = load_search_config(REPO_ROOT / "search_configs" / "ludwig_validation.yaml")
    fnd = _phrase_enum_block(cfg.block_a)
    imag = _phrase_enum_block(cfg.block_b)
    design = _phrase_enum_block(cfg.block_c)
    lang = ' AND (LANG:"eng")' if cfg.language_filter else ""
    date = f" AND (PUB_YEAR:[{fnd_meta_search._date_filter_year_range(cfg)}])"
    query = (
        f"(TITLE_ABS:({fnd})) AND (TITLE_ABS:({imag}))"
        f" AND (TITLE_ABS:({design})){lang}{date}"
    )
    # This validation query is short; tighten the limit so chunking engages.
    limit = EuropePMCClient._request_line_bytes(query, 1000) - 60
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(EuropePMCClient, "CURSOR_RESERVE_BYTES", 0)
        mp.setattr(EuropePMCClient, "MAX_REQUEST_LINE_BYTES", limit)
        plan = EuropePMCClient.plan_chunks(query, 1000)

    assert plan is not None and plan.n_chunks >= 2
    for chunk in plan.chunks:
        assert f"(TITLE_ABS:({design}))" in chunk
        assert f"(TITLE_ABS:({imag}))" in chunk


# ---------------------------------------------------------------------------
# Chunked path: union semantics, dedup, logging
# ---------------------------------------------------------------------------


def _force_chunking(monkeypatch, query: str, terms_to_drop: int = 3):
    """Shrink the request-line ceiling enough to force a multi-chunk plan."""
    term_cost = len(EuropePMCClient._encode_param("(symptom00*)")) + 4
    monkeypatch.setattr(EuropePMCClient, "CURSOR_RESERVE_BYTES", 0)
    monkeypatch.setattr(
        EuropePMCClient, "MAX_REQUEST_LINE_BYTES",
        EuropePMCClient._request_line_bytes(query, 1000) - terms_to_drop * term_cost,
    )


def test_chunked_search_returns_the_same_records_as_one_shot(monkeypatch):
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    term_hits = _term_hits_for(cfg)

    # one-shot reference
    one_shot_fake = _FakeEPMC(term_hits)
    monkeypatch.setattr(fms_requests, "get", one_shot_fake)
    one_shot = EuropePMCClient().search(query, page_size=3)
    assert len(one_shot_fake.urls) > 1  # pagination was exercised
    one_shot_ids = [r.source_id for r in one_shot]

    # chunked run over the same synthetic corpus
    _force_chunking(monkeypatch, query)
    assert EuropePMCClient.plan_chunks(query, 1000).n_chunks >= 2
    chunked_fake = _FakeEPMC(term_hits)
    monkeypatch.setattr(fms_requests, "get", chunked_fake)
    chunked = EuropePMCClient().search(query, page_size=3)

    chunked_ids = [r.source_id for r in chunked]
    assert chunked_ids == one_shot_ids          # union + stable chunk order
    assert len(set(chunked_ids)) == len(chunked_ids)  # no duplicates
    assert len(chunked) >= len(one_shot)
    # same Record shape
    assert [type(r) for r in chunked] == [type(r) for r in one_shot]
    assert chunked[0].__dict__.keys() == one_shot[0].__dict__.keys()


def test_chunked_search_dedups_on_source_and_id(monkeypatch):
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    term_hits = _term_hits_for(cfg)
    _force_chunking(monkeypatch, query)

    fake = _FakeEPMC(term_hits)
    monkeypatch.setattr(fms_requests, "get", fake)
    records = EuropePMCClient().search(query, page_size=1000)

    keys = [(r.url.rsplit("/", 2)[-2], r.source_id) for r in records]
    assert len(keys) == len(set(keys))
    # identical numeric id under a different EPMC source is a distinct record
    a = _fake_hit("dup", source="MED")
    b = _fake_hit("dup", source="PPR")
    assert EuropePMCClient._result_key(a) != EuropePMCClient._result_key(b)
    assert EuropePMCClient._result_key(a) == EuropePMCClient._result_key(dict(a))


def test_chunked_search_logs_chunk_provenance(monkeypatch, caplog):
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    _force_chunking(monkeypatch, query)
    monkeypatch.setattr(fms_requests, "get", _FakeEPMC(_term_hits_for(cfg)))

    with caplog.at_level(logging.INFO, logger="fnd_meta_search"):
        records = EuropePMCClient().search(query, page_size=1000)

    text = caplog.text
    split = re.search(r"splitting group (\d+) \[([^\]]+)\] into (\d+) chunks", text)
    assert split, text
    n_chunks = int(split.group(3))
    assert n_chunks >= 2
    chunk_lines = re.findall(r"chunk (\d+)/(\d+) hitCount=(\d+) retrieved=(\d+) new=(\d+)", text)
    assert len(chunk_lines) == n_chunks
    assert [int(c[0]) for c in chunk_lines] == list(range(1, n_chunks + 1))

    merged = re.search(
        r"merged (\d+) unique records from (\d+) chunks "
        r"\(summed chunk hitCount=(\d+), retrieved=(\d+), duplicates dropped=(\d+)\)",
        text,
    )
    assert merged, text
    merged_unique, plan_chunks, summed, retrieved, dropped = map(int, merged.groups())
    assert merged_unique == len(records)
    assert plan_chunks == n_chunks
    assert summed >= merged_unique          # required invariant
    assert retrieved - dropped == merged_unique
    assert dropped > 0                       # fixtures overlap on purpose


def test_sum_of_chunk_hitcounts_bounds_merged_total(monkeypatch, caplog):
    """sum(per-chunk hitCount) >= merged unique count — pinned with an all-fit split."""
    cfg = _small_config()
    query = build_europepmc_query(cfg)
    _force_chunking(monkeypatch, query, terms_to_drop=1)
    monkeypatch.setattr(fms_requests, "get", _FakeEPMC(_term_hits_for(cfg)))

    with caplog.at_level(logging.INFO, logger="fnd_meta_search"):
        records = EuropePMCClient().search(query, page_size=1000)

    hit_counts = [int(m) for m in re.findall(r"chunk \d+/\d+ hitCount=(\d+)", caplog.text)]
    assert hit_counts
    assert sum(hit_counts) >= len(records)


# ---------------------------------------------------------------------------
# Safety rails
# ---------------------------------------------------------------------------


def test_not_clause_is_never_split(monkeypatch):
    cfg = _small_config(exclude=["review", "meta-analysis", "case report"])
    query = build_europepmc_query(cfg)
    assert " NOT (" in query

    monkeypatch.setattr(EuropePMCClient, "CURSOR_RESERVE_BYTES", 0)
    monkeypatch.setattr(
        EuropePMCClient, "MAX_REQUEST_LINE_BYTES",
        EuropePMCClient._request_line_bytes(query, 1000) - 60,
    )
    plan = EuropePMCClient.plan_chunks(query, 1000)
    assert plan is not None

    conj = _split_conjuncts(query)
    not_index = next(i for i, (sep, _t) in enumerate(conj) if sep == " NOT ")
    assert plan.group_index != not_index
    not_clause = conj[not_index][1]
    for chunk in plan.chunks:
        assert not_clause in chunk


def test_single_oversized_term_raises_actionable_error():
    cfg = SearchConfig(
        block_a=["x" * 9000, "short term"],
        block_b=["imaging*"],
        date_start=None,
        date_end="2026/12/31",
        language_filter=True,
    )
    query = build_europepmc_query(cfg)
    with pytest.raises(QueryTooLongError) as excinfo:
        EuropePMCClient.plan_chunks(query, 1000)
    message = str(excinfo.value)
    assert "per-chunk budget" in message
    assert "shorten the term" in message


def test_query_without_splittable_or_group_raises_actionable_error():
    cfg = SearchConfig(
        block_a=["x" * 4000],
        block_b=["y" * 4000],
        date_start=None,
        date_end="2026/12/31",
        language_filter=False,
    )
    query = build_europepmc_query(cfg)
    with pytest.raises(QueryTooLongError) as excinfo:
        EuropePMCClient.plan_chunks(query, 1000)
    assert "no multi-term positive OR-group" in str(excinfo.value)
