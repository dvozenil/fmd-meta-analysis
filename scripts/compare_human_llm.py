#!/usr/bin/env python3
"""Compare human screening decisions with LLM decisions from the sample CSV.

Usage:
    python scripts/compare_human_llm.py data/human_screening_sample_50_DONE.csv
"""

import argparse
import csv
from pathlib import Path


def detect_delimiter(path: Path) -> str:
    """Sniff CSV delimiter from the first line."""
    with path.open(encoding="utf-8") as f:
        header = f.readline()
    if header.count(";") > header.count(","):
        return ";"
    return ","


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()

    delim = detect_delimiter(args.csv_file)
    with args.csv_file.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=delim))

    screened = [r for r in rows if r.get("human_decision", "").strip()]
    unscreened = len(rows) - len(screened)

    if not screened:
        print("No human decisions found. Fill in the human_decision column first.")
        print(f"  (detected delimiter: {delim!r}; columns found: {list(rows[0].keys()) if rows else 'none'})")
        return

    print(f"Total rows:     {len(rows)}")
    print(f"Screened:       {len(screened)}")
    if unscreened:
        print(f"Not screened:   {unscreened}")

    # ── Decision distributions ───────────────────────────────────────
    from collections import Counter
    h_dist = Counter(r["human_decision"].strip().lower() for r in screened)
    l_dist = Counter(r["llm_decision"].strip().lower() for r in screened)

    print(f"\n{'=' * 60}")
    print("  DECISION DISTRIBUTIONS")
    print(f"{'=' * 60}")
    all_decs = sorted(set(list(h_dist.keys()) + list(l_dist.keys())))
    print(f"  {'decision':25s} {'Human':>8s} {'LLM':>8s}")
    for d in all_decs:
        print(f"  {d:25s} {h_dist.get(d, 0):8d} {l_dist.get(d, 0):8d}")

    # ── Exact agreement ──────────────────────────────────────────────
    agree = sum(1 for r in screened
                if r["human_decision"].strip().lower() == r["llm_decision"].strip().lower())
    pct = agree / len(screened)
    print(f"\n{'=' * 60}")
    print("  EXACT AGREEMENT (3-way: include / exclude / unclear)")
    print(f"{'=' * 60}")
    print(f"  Agreement:    {agree}/{len(screened)} ({pct:.1%})")

    # ── 3-way confusion matrix ───────────────────────────────────────
    labels = ["include_candidate", "unclear", "exclude"]
    matrix = {h: {l: 0 for l in labels} for h in labels}
    for r in screened:
        h = r["human_decision"].strip().lower()
        l = r["llm_decision"].strip().lower()
        if h in matrix and l in matrix[h]:
            matrix[h][l] += 1

    print(f"\n{'=' * 60}")
    print("  3-WAY CONFUSION MATRIX  (rows = Human, cols = LLM)")
    print(f"{'=' * 60}")
    header = f"  {'':20s}" + "".join(f"{'LLM:' + l:>20s}" for l in labels)
    print(header)
    for h in labels:
        row = f"  {'H:' + h:20s}" + "".join(f"{matrix[h][l]:20d}" for l in labels)
        print(row)

    # ── Binary metrics (include/unclear vs exclude) ──────────────────
    # Treat human "unclear" as "would-keep" since you defer for later review
    tp = fp = fn = tn = 0
    for r in screened:
        h_keep = r["human_decision"].strip().lower() in ("include_candidate", "unclear")
        l_keep = r["llm_decision"].strip().lower() in ("include_candidate", "unclear")
        if h_keep and l_keep:
            tp += 1
        elif not h_keep and not l_keep:
            tn += 1
        elif l_keep and not h_keep:
            fp += 1
        else:
            fn += 1

    print(f"\n{'=' * 60}")
    print("  BINARY METRICS  (keep = include+unclear  vs  exclude)")
    print(f"{'=' * 60}")
    print(f"  TP (both keep):       {tp}")
    print(f"  TN (both exclude):    {tn}")
    print(f"  FP (LLM keep, H exc): {fp}")
    print(f"  FN (LLM exc, H keep): {fn}")

    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    ppv = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")
    print(f"\n  Sensitivity (LLM catches what human keeps): {sens:.1%}")
    print(f"  Specificity (LLM excludes what human excludes): {spec:.1%}")
    print(f"  PPV (when LLM keeps, human agrees):             {ppv:.1%}")
    print(f"  NPV (when LLM excludes, human agrees):          {npv:.1%}")

    # ── Disagreement analysis ────────────────────────────────────────
    disagree = [r for r in screened
                if r["human_decision"].strip().lower() != r["llm_decision"].strip().lower()]

    if not disagree:
        print("\nNo disagreements!")
        return

    # Categorize disagreements
    h_unclear_l_inc = []
    h_unclear_l_exc = []
    h_exc_l_inc = []
    h_inc_l_exc = []
    other_disagree = []

    for r in disagree:
        h = r["human_decision"].strip().lower()
        l = r["llm_decision"].strip().lower()
        if h == "unclear" and l == "include_candidate":
            h_unclear_l_inc.append(r)
        elif h == "unclear" and l == "exclude":
            h_unclear_l_exc.append(r)
        elif h == "exclude" and l == "include_candidate":
            h_exc_l_inc.append(r)
        elif h == "include_candidate" and l == "exclude":
            h_inc_l_exc.append(r)
        else:
            other_disagree.append(r)

    def _print_records(recs: list[dict], label: str) -> None:
        if not recs:
            return
        print(f"\n--- {label} ({len(recs)}) ---")
        for r in recs:
            title = r.get("title", "?")[:80]
            h_note = r.get("human_notes", "").strip()
            l_reason = r.get("llm_reason", "")[:120]
            pop = r.get("llm_population_tags", "")
            mod = r.get("llm_modality_tags", "")
            print(f"\n  {r['record_id']}")
            print(f"    {title}")
            if h_note:
                print(f"    You:  {h_note}")
            print(f"    LLM:  {l_reason}")
            if pop or mod:
                print(f"    Tags: pop={pop}  mod={mod}")

    print(f"\n{'=' * 60}")
    print(f"  ALL DISAGREEMENTS ({len(disagree)} total)")
    print(f"{'=' * 60}")

    _print_records(h_unclear_l_inc,
                   "You said UNCLEAR, LLM said INCLUDE — cautious human vs confident LLM")
    _print_records(h_unclear_l_exc,
                   "You said UNCLEAR, LLM said EXCLUDE — you'd keep for review, LLM would drop")
    _print_records(h_exc_l_inc,
                   "You said EXCLUDE, LLM said INCLUDE — potential LLM over-inclusion")
    _print_records(h_inc_l_exc,
                   "You said INCLUDE, LLM said EXCLUDE — potential LLM miss (most concerning)")
    _print_records(other_disagree, "Other disagreements")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  You used 'unclear' {h_dist.get('unclear', 0)} times; LLM used it {l_dist.get('unclear', 0)} times.")
    print(f"  Of your {h_dist.get('unclear', 0)} 'unclear' calls:")
    if h_unclear_l_inc:
        print(f"    {len(h_unclear_l_inc)} the LLM confidently included")
    if h_unclear_l_exc:
        print(f"    {len(h_unclear_l_exc)} the LLM confidently excluded")
    n_unclear_agree = h_dist.get("unclear", 0) - len(h_unclear_l_inc) - len(h_unclear_l_exc)
    if n_unclear_agree:
        print(f"    {n_unclear_agree} the LLM also marked unclear")
    if h_exc_l_inc:
        print(f"  Hard disagreements (you exclude, LLM includes): {len(h_exc_l_inc)}")
    if h_inc_l_exc:
        print(f"  *** LLM MISSES (you include, LLM excludes): {len(h_inc_l_exc)} ***")


if __name__ == "__main__":
    main()
