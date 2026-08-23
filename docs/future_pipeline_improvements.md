# Future Pipeline Improvements (Planning)

Author: phd profile, at David's request
Date: 2026-08-02
Status: **Deferred backlog** — NOT blockers for the current (2026-07-31/08-02) corpus
freeze. The dataset is freeze-approved; these are structural improvements for
future runs of this pipeline, safe to schedule later.

## Why this exists

During the round-1/round-2 review of the dedup pipeline fixes, several
structural weaknesses surfaced that are *not* bugs in the current data but
would make future harvests more robust, more modular, and less foot-gun-prone.
This document records them as a planned backlog so the knowledge isn't lost.

---

## 1. Modular per-database search (high value)

**Status: DONE (issue #8, PR #9)** — `--db` flag and YAML config system implemented.

**Problem:** `run_searches()` always fires all 4 API clients (pubmed, europepmc,
wos, scopus) plus the EBSCO psycinfo import. There is no CLI flag to harvest a
single database (e.g. `--db pubmed`). This is why targeted regenerations (the
`regenerate_raw_pubmed.py` / `regenerate_raw_europepmc.py` ad-hoc scripts) had to
be written by hand.

**Why it matters:**
- Targeted re-fetch of one DB after a parser/query fix, without touching the
  other DBs' raw exports.
- Onboarding additional databases becomes a clean per-client addition rather
  than nested orchestration.
- Test/reproduce a single source in isolation.

**Proposed design:**
- Add `--db <name>` (repeatable) to select subset of databases; default = all.
- Each DB client already has a uniform `.search(query) -> list[Record]`
  interface, so thread selection through the `clients` dict construction.
- Have the search phase write only the selected DBs' `raw_<db>.csv` (and the
  shared `queries.json`).
- The existing decoupled `--dedup <dir>` already re-reads whatever raw CSVs are
  present, so a single-DB search + full dedup already works conceptually.

**Benefit over ad-hoc scripts:** once `--db` exists, the `regenerate_raw_*.py`
scripts become a thin wrapper or are retired.

---

## 2. Canonical raw-source selection — kill the double-load foot-guns (high value)

**Problem (round-2 W2):** a database's records can exist in multiple formats in
the search dir (WoS as `raw_wos.csv`, `raw_savedrecs*.csv`, and `savedrecs*.ris`).
The dedup's skip of `raw_savedrecs*.csv` is *conditional on the `.ris` files
being present* (`ris_present` at `fnd_meta_search.py:1820`). If the RIS files
are ever removed, the next `--dedup` silently double-loads WoS (raw inflates to
9,153). This is a latent foot-gun, not a current bug.

Related: `raw_pubmed.OLD.csv` / `raw_europepmc.OLD.csv` backups (from the regen
scripts) are also matched by the `raw_*.csv` glob and contaminated a run earlier.

**Proposed design — a canonical staging layout:**
- Add a `raw/` subfolder (or a `.ignore` list) that holds *only* the
  authoritative per-DB `raw_<db>.csv` files.
- Dedup collects from the canonical location; legacy/non-authoritative leftovers
  (`raw_savedrecs*.csv`, `*.OLD.csv`) live outside and are never globbed.
- Failing a full restructure, at minimum: hard-code "savedrecs CSVs are never
  primary when `raw_wos.csv` exists", independent of RIS presence.
- Optional: after a successful dedup, auto-archive non-authoritative leftovers
  and any `.OLD` backups into an `archive/` dir.

**Benefit:** a future `--dedup` cannot silently double-count a database based on
which files happen to be on disk.

---

## 3. Lazy CLI argument parsing — import-safe module (medium value)

**Problem (round-1 S3 / round-2 W1):** `_parse_args()` runs at module import
(`fnd_meta_search.py:120`), so *any* import of the module (bare `pytest`
collection, other scripts importing `Record` / clients) triggers argparse
`SystemExit:2`. Bare `python3 -m pytest` currently fails to collect; the 70/70
suite only passes with a sanitized argv. Side effect: importing creates an empty
`./fnd_search_<ts>/` output dir.

**Proposed design:**
- Guard CLI parsing and the `if DEDUP_ONLY_DIR:` config block under
  `if __name__ == "__main__":` or move config resolution into a lazy
  `get_config()` accessor called from the entry point.
- Module-level globals (`AUTO_MODE`, `DEDUP_METHOD`, etc.) become derived from a
  single parsed-config object rather than parsed at import.
- This is a moderate refactor; doing it also removes the stray `./fnd_search_<ts>/`
  litter and makes the module import-safe for CI and library use.

**Deferred** because it is non-blocking (the CLI works; tests pass with a
sanitized-argv workaround) and touches shared module structure — risky to do
right at a corpus freeze.

---

## 4. Central list of non-primary/mechanical duplicate populations (medium value)

**Problem (round-1 W1 / round-2 disposition):** ~50 of the 104 maybe-pairs are
mechanical re-indexing duplicates (WoS `GRANTS:*` non-primary, `PQDT:*`
dissertations, `BCI:*`/`MEDLINE:*` vs core WoS) that get re-identified and
re-dispositioned by hand every run. A human reviewed and stratified these once;
that knowledge isn't captured in code.

**Proposed design:**
- Add an inclusion/exclusion rule table (or config) encoding these populations
  (GRANTS => non-primary -> exclude at screening; PQDT/BCI/MEDLINE => merge
  with core WoS copy when identical).
- Have maybe-pairs export flag each pair with its predicted stratum so the human
  adjudication starts from a pre-classified state instead of from scratch.

---

## 5. Abstract-recovery policy — explicit freeze decision (low/medium value)

**Problem:** 458/3553 (12.9%) records lack abstracts; round-2 ran
`--skip-abstract-recovery` so counts are frozen. Re-running without that flag
would recover more but **change the counts**, so it must be a deliberate,
documented decision at freeze time rather than an afterthought.

**Proposed design:**
- Add a `--recover-abstracts` explicit flag (or a documented PRISMA note) so the
  choice is visible in the metadata, not implied by omitting a skip flag.
- Consider recovering abstracts for the final corpus once pairwise adjudication
  is done, then re-freezing once — to avoid mid-screening count churn.

---

## 6. Test invocation ergonomics (low value, quick)

- The standalone runner (`python test_dedup_asysd.py`) and the argv-guarded
  pytest invocation both pass 70/70, but there's no single canonical command and
  no CI wiring.
- Add a small `Makefile`/`pytest.ini` aliased to the sanitized-argv invocation,
  or fix #3 and use plain `pytest`.
- Document the sanitized-argv requirement until #3 lands.

---

## Suggested priority for a future sprint

1. **#2 canonical raw-source selection** — prevents silent data corruption in
   the next harvest (highest safety value).
2. **#1 modular per-DB search** — removes the need for ad-hoc regen scripts and
   makes future DB changes clean.
3. **#3 lazy argparse** — import-safe module + removes litter + unblocks plain
   pytest CI.
4. **#4 duplicate-population table** — makes maybe-pair adjudication repeatable.
5. **#5 abstract-recovery policy** — document + one clean re-freeze.
6. **#6 test ergonomics** — wrap once #3 is in.

---

## Explicitly out of scope / not applied now

- These are **not** applied to the current frozen corpus (`fnd_search_20260731_193704_retest2`,
  3,553 unique, freeze-approved). The current data is complete and reproducible;
  applying any of this now would risk churn right before screening starts.
- Review docs, the regen scripts' `.OLD` backups, and ad-hoc test artifacts
  are **not** intended for the remote repo — they live in `/shared` / the search
  folder for audit, not in git.
