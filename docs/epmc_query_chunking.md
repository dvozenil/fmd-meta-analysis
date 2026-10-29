# Europe PMC query chunking (URL-length fallback)

How `EuropePMCClient.search()` in `fnd_meta_search.py` handles a rendered
query that is too long for the Europe PMC REST endpoint, and why that is
recall-neutral.

## The constraint

Europe PMC's REST search is **GET-only** — a POST to the same endpoint answers
`405 Method Not Allowed` (verified 2026-10-29) — and it sits behind a Tomcat
front-end that rejects long request lines with a bare error instead of a
useful API response:

| Date | Query | Rendered bytes | Result |
|---|---|---|---|
| 2026-10-19 | Martin's v2 draft (paren-heavy wildcard blocks) | ~7.9 k | bare HTTP **400** |
| 2026-10-29 | `full` mode, quoted-phrase enumeration | 8,397 | HTTP **414 URI Too Long** |

`EuropePMCClient._encode_param` already trims the request line (parentheses
and `*` sent raw, `+` for spaces) and keeps the current production `full`
query at 3,998 bytes. That is enough for the assembled term lists *today*, but
the ceiling is a function of the term list, not of anything the client
controls: the phrase-enumeration rendering recommended by the EPMC recall
audit (`"functional motor disorder" OR "functional motor disorders"` …)
expands the same query to 8,397 bytes and is rejected outright.

## What the client does

When `plan_chunks(query)` finds the rendered query does not fit
`EuropePMCClient.MAX_REQUEST_LINE_BYTES` (7,500 B — a conservative margin
below Tomcat's ~8 KB), `search()` splits **one positive OR-group at term
boundaries** and unions the results:

```
(A1 OR A2 OR … OR An) AND (B) AND filters
    ==  union over chunks of [ (A_chunk) AND (B) AND filters ]
```

That is the distributive law, so the retrieved record set is *identical* to
what the single request would have returned — this is a transport-layer
change with no recall effect and no change to how any term is rendered.

Properties of the split:

- **One group only.** The largest positive OR-group is chosen, because it
  buys the most shrink per chunk. `NOT` (exclusion) clauses are never split:
  `NOT (A OR B)` is not `NOT A ∪ NOT B`.
- **Term-level, never mid-term.** A term stays intact even if it nests an AND,
  e.g. the `mri_fallback` arm `("magnetic" AND "resonance" AND "imaging")`.
- **Budget derived from the real query.** The client measures the *encoded*
  bytes of everything that is not the split group (other OR-groups, language
  and year filters, parameter names) and gives the group only the remainder.
  There is no hardcoded character budget; `_encode_param` is character-wise,
  so encoded lengths add up exactly across a concatenation.
- **Balanced packing.** Terms keep their order and are packed into contiguous
  groups targeting an equal share of the term weight, then verified against
  the byte budget (extra chunks are added if a group still does not fit).
- **Filter clauses are untouched.** The other groups, `LANG:`, `PUB_YEAR:`
  and any `NOT` clause appear verbatim in every chunk (`tests/test_epmc_query_chunking.py`
  asserts this byte-for-byte).

### Merge and dedup

Chunks can return the same article when it matches terms in more than one
chunk, so the merged path deduplicates on **`(source, id)`** — Europe PMC's
own result identity (`EuropePMCClient._result_key`). Rationale:

- Within one EPMC search the only possible duplicates are the same article
  returned by different chunk requests, and EPMC always reports that article
  with the same `source` + `id` pair. The key therefore cannot merge two
  distinct records.
- The audit prototype deduplicated on `(id, source, norm_title, norm_doi)`.
  Title/DOI components are unnecessary here and are actively risky: records
  without a DOI would all share `norm_doi = None`, and title normalization is
  a cross-database dedup concern (`dedup_asysd.py`) that this layer must not
  pre-empt.

Result order is chunk order, then EPMC result order within a chunk; it is
deterministic for a given plan. The plan itself is a pure function of
`(query, page_size)` and the two class constants, so the original query in
`queries.json` plus the run log's chunk line is enough to reconstruct the
exact chunk strings (they are also emitted at DEBUG level).

Queries that fit never enter this path: `search()` issues the same single
`requests.get()` with the same URL as before chunking existed, and returns
`Record`s in EPMC order without a dedup pass. Short-query output is therefore
byte-identical to the pre-chunking implementation (pinned by a golden test).

### Provenance logging (PRISMA-S)

Every chunked search writes its plan and its outcome to the run log, so a
search record stays auditable:

```
Europe PMC: query needs 8397 B of request line (limit 7500 B) — splitting group 1 [TITLE_ABS] into 2 chunks [terms per chunk: 72, 72; chunk request lines: 6092, 6157 B]
Europe PMC: chunk 1/2 hitCount=490 retrieved=490 new=490 unique-so-far=490
Europe PMC: chunk 2/2 hitCount=623 retrieved=623 new=548 unique-so-far=1038
Europe PMC: merged 1038 unique records from 2 chunks (summed chunk hitCount=1113, retrieved=1113, duplicates dropped=75)
```

`summed chunk hitCount ≥ merged unique` always holds (each chunk reports its
own total; the merge collapses cross-chunk duplicates).

### When it still fails

`QueryTooLongError` (a `ValueError`) is raised, before any request is sent,
when the query cannot be made to fit:

- a single term is longer than the per-chunk budget — the message names the
  term, since shortening it is the only fix;
- the query has no multi-term positive OR-group to split;
- the *non-split* remainder alone is already oversized. Handling that would
  require chunking a second OR-group, i.e. a cross-product of chunk sets,
  which this layer deliberately does not attempt.

## What this does not do

- **No rendering change.** Which form each term takes (quoted phrase, unquoted
  wildcard, enumerated plural) is decided by `build_europepmc_query()` and its
  per-block renderers. Quoted-wildcard rendering in particular is a separate,
  PI-pending decision; chunking only makes whatever rendering exists
  transportable.
- **No cross-database dedup.** Chunk dedup is `(source, id)` only; the
  cross-database pass stays in `run_searches()` / `dedup_asysd.py`.
- **No output-schema change.** Chunked and single-request paths return the
  same `list[Record]`.

## Verification

`tests/test_epmc_query_chunking.py` (offline, `requests.get` replaced by a
small EPMC stand-in) pins:

- golden: a fitting query issues exactly one GET with the pre-chunking URL and
  returns records in EPMC order;
- the split is a partition — every term in exactly one chunk, order preserved,
  prefix/suffix identical, non-split clauses byte-identical across chunks;
- every chunk request line fits, with the budget derived from the actual
  remaining query (padding the query with unrelated clauses forces more
  chunks at the same absolute limit);
- chunked and one-shot result sets agree, duplicates collapse, and the
  per-chunk `hitCount` logs satisfy `sum(hitCount) ≥ merged unique`;
- `NOT` is never split; impossible queries raise `QueryTooLongError`.

Live checks against the real endpoint (2026-10-29):

- unsplit phrase-enum query: 8,397 B → HTTP 414 (the failure this replaces);
- chunked: 6,092 B + 6,157 B → `hitCount` 490 + 623 → **1,038 unique
  records**, 75 cross-chunk duplicates dropped;
- a different partition of the same terms (10 chunks at a 4,600 B limit)
  returned the **identical 1,038-record set** — partition independence, i.e.
  the union really is exact;
- the unchanged production `full` query (3,998 B) still takes the
  single-request path: `plan_chunks()` → `None`, 24,864 records.
