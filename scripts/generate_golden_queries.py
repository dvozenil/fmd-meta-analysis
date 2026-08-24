#!/usr/bin/env python3
"""Generate golden query baselines for all 5 search modes.

The golden baselines are byte-identical reference files that the T3
regression tests check against. They are produced by calling the query
builder functions directly -- no API keys needed, because queries are
built before any API call fires.

For each mode we set the module-level ``SEARCH_MODE`` / ``SEARCH_START_YEAR`` /
``SEARCH_END_DATE`` globals that ``fnd_meta_search.py``'s builders read, then
serialise the resulting queries in the exact same layout as ``run_searches()``
(dict order: pubmed, europepmc, wos, scopus, ebsco_psycinfo, then the
``_search_*`` metadata keys; ``queries.json`` with ``indent=2``; ``queries.txt``
with ``--- <db> ---`` separators).

Dates are pinned to fixed values so the files are stable no matter when they
are regenerated:

    update          start 2015           end 2026/07/31
    full            inception            end 2026/07/31
    os_validation   inception            end 2015/08/31
    os_table_recall inception            end 2015/08/31
    ludwig_validation inception          end 2016/11/04

Output: tests/golden/<mode>/queries.json and tests/golden/<mode>/queries.txt
"""

import json
import sys
from pathlib import Path

# fnd_meta_search.py calls _parse_args() at import time, so patch argv to a
# valid set before importing it (mirrors the conftest.py sanitization).
sys.argv = ["fnd_meta_search", "--full", "--no-dedup", "--auto"]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fnd_meta_search as fms  # noqa: E402  (import order is intentional)

MODES = {
    "update": {"start_year": 2015, "end_date": "2026/07/31"},
    "full": {"start_year": None, "end_date": "2026/07/31"},
    "os_validation": {"start_year": None, "end_date": "2015/08/31"},
    "os_table_recall": {"start_year": None, "end_date": "2015/08/31"},
    "ludwig_validation": {"start_year": None, "end_date": "2016/11/04"},
}

BUILDERS = [
    ("pubmed", fms.build_pubmed_query),
    ("europepmc", fms.build_europepmc_query),
    ("wos", fms.build_wos_query),
    ("scopus", fms.build_scopus_query),
    ("ebsco_psycinfo", fms.build_ebsco_psycinfo_query),
]


def build_queries(mode: str) -> dict:
    """Build and return the full queries dict for *mode*.

    Config end dates are pinned via ``date_end_override`` because the committed
    ``update``/``full`` YAMLs now use the dynamic ``"today"`` sentinel — without
    the pin, a regeneration would silently embed the run date instead of the
    stable golden reference dates.
    """
    cfg = MODES[mode]
    config = fms.load_search_config(
        ROOT / "search_configs" / f"{mode}.yaml",
        date_end_override=cfg["end_date"],
    )

    queries = {name: builder(config) for name, builder in BUILDERS}
    queries["_search_mode"] = mode
    queries["_search_start_year"] = cfg["start_year"]
    queries["_search_end_date"] = cfg["end_date"]
    return queries


def write_golden(mode: str, queries: dict) -> Path:
    out_dir = ROOT / "tests" / "golden" / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "queries.json", "w", encoding="utf-8") as f:
        json.dump(queries, f, indent=2)

    with open(out_dir / "queries.txt", "w", encoding="utf-8") as f:
        # Mirror run_searches(): only real query strings, no "_search_*" metadata.
        for db, q in queries.items():
            if db.startswith("_"):
                continue
            f.write(f"--- {db} ---\n{q}\n\n")

    return out_dir


def main() -> None:
    for mode in MODES:
        out_dir = write_golden(mode, build_queries(mode))
        q = json.loads((out_dir / "queries.json").read_text(encoding="utf-8"))
        cfg = MODES[mode]
        fnd_n = len(fms._active_term_config().block_a)
        print(
            f"[{mode:16s}] cfg={cfg} -> {len(q)} keys "
            f"({fnd_n} FND terms) in {out_dir.relative_to(ROOT)}"
        )


if __name__ == "__main__":
    main()
