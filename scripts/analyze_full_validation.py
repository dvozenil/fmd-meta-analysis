#!/usr/bin/env python3
"""Deep-dive analysis of the full validation screening results.

Usage:
    python scripts/analyze_full_validation.py data/pilot/qwen3_5_122b_thinking_off_FULL-VALIDATION.jsonl
"""

import argparse
import json
import random
import csv
from collections import Counter
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open() if l.strip()]


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def subsection(title: str) -> None:
    print(f"\n--- {title} ---")


def analyze(records: list[dict]) -> None:
    decisions = Counter(r["llm_decision"]["decision"] for r in records if r.get("llm_decision"))
    total = len(records)

    # ── 1. Overall decision breakdown ────────────────────────────────
    section("1. OVERALL DECISION BREAKDOWN")
    for dec, count in decisions.most_common():
        print(f"  {dec:25s}  {count:4d}  ({count / total:.1%})")
    print(f"  {'TOTAL':25s}  {total:4d}")

    includes = [r for r in records if r.get("llm_decision", {}).get("decision") == "include_candidate"]
    excludes = [r for r in records if r.get("llm_decision", {}).get("decision") == "exclude"]
    unclears = [r for r in records if r.get("llm_decision", {}).get("decision") == "unclear"]

    # ── 2. Unclear bucket ────────────────────────────────────────────
    section("2. UNCLEAR BUCKET")
    print(f"  Total unclear: {len(unclears)}")
    if unclears:
        subsection("Confidence distribution (unclear)")
        confs = [r["llm_decision"]["confidence"] for r in unclears]
        for bucket_label, lo, hi in [("0.0–0.3", 0, 0.3), ("0.3–0.5", 0.3, 0.5),
                                      ("0.5–0.7", 0.5, 0.7), ("0.7–1.0", 0.7, 1.01)]:
            n = sum(1 for c in confs if lo <= c < hi)
            print(f"    {bucket_label}: {n}")

        subsection("Population tags on unclear records")
        pop_tags = Counter(
            tag for r in unclears for tag in r["llm_decision"].get("population_tags", [])
        )
        for tag, cnt in pop_tags.most_common():
            print(f"    {tag:30s}  {cnt}")
        no_pop = sum(1 for r in unclears if not r["llm_decision"].get("population_tags"))
        print(f"    {'(no population tag)':30s}  {no_pop}")

        subsection("Modality tags on unclear records")
        mod_tags = Counter(
            tag for r in unclears for tag in r["llm_decision"].get("modality_tags", [])
        )
        for tag, cnt in mod_tags.most_common():
            print(f"    {tag:30s}  {cnt}")
        no_mod = sum(1 for r in unclears if not r["llm_decision"].get("modality_tags"))
        print(f"    {'(no modality tag)':30s}  {no_mod}")

        subsection("All unclear records")
        for r in sorted(unclears, key=lambda x: x["llm_decision"]["confidence"]):
            d = r["llm_decision"]
            title = r.get("input_record", {}).get("title", "?")[:70]
            ref = r.get("input_record", {}).get("os_study_ref", "") or ""
            gold = r.get("input_record", {}).get("human_gold_decision", "") or ""
            pops = ", ".join(d.get("population_tags", []))
            mods = ", ".join(d.get("modality_tags", []))
            print(f"  [{d['confidence']:.2f}] {r['record_id']}")
            print(f"         {title}")
            if ref:
                print(f"         OS ref: {ref}")
            if gold:
                print(f"         Gold: {gold}")
            print(f"         Pop: {pops or '(none)'}  |  Mod: {mods or '(none)'}")
            print(f"         Reason: {d['reason'][:120]}")
            print()

    # ── 3. Population tags analysis ──────────────────────────────────
    section("3. POPULATION TAGS ANALYSIS")

    subsection("Population tag frequency across ALL records")
    all_pop = Counter(
        tag for r in records for tag in r.get("llm_decision", {}).get("population_tags", [])
    )
    for tag, cnt in all_pop.most_common():
        print(f"    {tag:30s}  {cnt}")
    no_pop_all = sum(1 for r in records if not r.get("llm_decision", {}).get("population_tags"))
    print(f"    {'(no population tag)':30s}  {no_pop_all}")

    subsection("FND-population-tagged records by decision")
    fnd_tagged = [r for r in records
                  if "FND" in r.get("llm_decision", {}).get("population_tags", [])]
    fnd_decisions = Counter(r["llm_decision"]["decision"] for r in fnd_tagged)
    for dec, cnt in fnd_decisions.most_common():
        print(f"    {dec:25s}  {cnt}")
    print(f"    {'TOTAL FND-tagged':25s}  {len(fnd_tagged)}")

    subsection("FND-tagged but EXCLUDED — exclusion reasons")
    fnd_excluded = [r for r in fnd_tagged if r["llm_decision"]["decision"] == "exclude"]
    excl_reasons = Counter(r["llm_decision"].get("exclusion_reason", "?") for r in fnd_excluded)
    for reason, cnt in excl_reasons.most_common():
        print(f"    {str(reason):30s}  {cnt}")

    subsection("FND-tagged, excluded — sample records")
    for r in fnd_excluded[:15]:
        d = r["llm_decision"]
        title = r.get("input_record", {}).get("title", "?")[:70]
        print(f"  {r['record_id']:28s} excl={d.get('exclusion_reason', '?'):20s}")
        print(f"    {title}")
        print(f"    Reason: {d['reason'][:120]}")
        print(f"    Modality: {', '.join(d.get('modality_tags', []))}")
        print()

    # ── 4. Include candidates analysis ───────────────────────────────
    section("4. INCLUDE CANDIDATES")
    print(f"  Total include_candidate: {len(includes)}")

    subsection("Modality tags on includes")
    inc_mod = Counter(
        tag for r in includes for tag in r["llm_decision"].get("modality_tags", [])
    )
    for tag, cnt in inc_mod.most_common():
        print(f"    {tag:30s}  {cnt}")

    subsection("Population tags on includes")
    inc_pop = Counter(
        tag for r in includes for tag in r["llm_decision"].get("population_tags", [])
    )
    for tag, cnt in inc_pop.most_common():
        print(f"    {tag:30s}  {cnt}")

    subsection("Design tags on includes")
    inc_des = Counter(
        tag for r in includes for tag in r["llm_decision"].get("design_tags", [])
    )
    for tag, cnt in inc_des.most_common():
        print(f"    {tag:30s}  {cnt}")

    subsection("Coordinate presence on includes")
    inc_coord = Counter(r["llm_decision"].get("coordinate_present", "?") for r in includes)
    for val, cnt in inc_coord.most_common():
        print(f"    {str(val):30s}  {cnt}")

    subsection("Confidence distribution on includes")
    inc_confs = [r["llm_decision"]["confidence"] for r in includes]
    for bucket_label, lo, hi in [("0.5–0.7", 0.5, 0.7), ("0.7–0.8", 0.7, 0.8),
                                  ("0.8–0.9", 0.8, 0.9), ("0.9–1.0", 0.9, 1.01)]:
        n = sum(1 for c in inc_confs if lo <= c < hi)
        print(f"    {bucket_label}: {n}")

    subsection("All include_candidate records")
    for r in sorted(includes, key=lambda x: x["llm_decision"]["confidence"]):
        d = r["llm_decision"]
        inp = r.get("input_record", {})
        title = inp.get("title", "?")[:70]
        ref = inp.get("os_study_ref", "") or ""
        gold = inp.get("human_gold_decision", "") or ""
        pops = ", ".join(d.get("population_tags", []))
        mods = ", ".join(d.get("modality_tags", []))
        coords = d.get("coordinate_present", "?")
        print(f"  [{d['confidence']:.2f}] {r['record_id']}")
        print(f"         {title}")
        if ref:
            print(f"         OS ref: {ref}")
        if gold:
            print(f"         Gold: {gold}")
        print(f"         Pop: {pops}  |  Mod: {mods}  |  Coords: {coords}")
        print(f"         Reason: {d['reason'][:120]}")
        print()

    # ── 5. Exclusion reason breakdown ────────────────────────────────
    section("5. EXCLUSION REASON BREAKDOWN")
    excl_reasons_all = Counter(
        r["llm_decision"].get("exclusion_reason", "?") for r in excludes
    )
    for reason, cnt in excl_reasons_all.most_common():
        print(f"    {str(reason):30s}  {cnt:4d}  ({cnt / len(excludes):.1%})")

    # ── 6. OS gold-labelled records check ────────────────────────────
    section("6. GOLD-LABELLED RECORDS (OS TABLE)")
    gold_records = [r for r in records if r.get("input_record", {}).get("human_gold_decision")]
    print(f"  Total gold-labelled: {len(gold_records)}")
    for gold_type in ["include_candidate", "include_broad_scope"]:
        subset = [r for r in gold_records
                  if r["input_record"]["human_gold_decision"] == gold_type]
        if not subset:
            continue
        llm_inc = [r for r in subset
                   if r["llm_decision"]["decision"] == "include_candidate"]
        llm_uncl = [r for r in subset
                    if r["llm_decision"]["decision"] == "unclear"]
        llm_excl = [r for r in subset
                    if r["llm_decision"]["decision"] == "exclude"]
        print(f"\n  Gold = {gold_type} ({len(subset)} records):")
        print(f"    LLM include:  {len(llm_inc)}")
        print(f"    LLM unclear:  {len(llm_uncl)}")
        print(f"    LLM exclude:  {len(llm_excl)}")

    # ── 7. Confidence calibration ────────────────────────────────────
    section("7. CONFIDENCE DISTRIBUTION (ALL RECORDS)")
    all_confs = [r["llm_decision"]["confidence"] for r in records if r.get("llm_decision")]
    for bucket_label, lo, hi in [("0.0–0.5", 0, 0.5), ("0.5–0.7", 0.5, 0.7),
                                  ("0.7–0.8", 0.7, 0.8), ("0.8–0.9", 0.8, 0.9),
                                  ("0.9–1.0", 0.9, 1.01)]:
        n = sum(1 for c in all_confs if lo <= c < hi)
        print(f"    {bucket_label}: {n:4d}")

    subsection("Low-confidence excludes (< 0.7)")
    low_conf_excl = [r for r in excludes if r["llm_decision"]["confidence"] < 0.7]
    print(f"  Count: {len(low_conf_excl)}")
    for r in low_conf_excl:
        d = r["llm_decision"]
        title = r.get("input_record", {}).get("title", "?")[:70]
        pops = ", ".join(d.get("population_tags", []))
        print(f"  [{d['confidence']:.2f}] {r['record_id']}")
        print(f"         {title}")
        print(f"         Excl: {d.get('exclusion_reason')}  |  Pop: {pops}")
        print(f"         Reason: {d['reason'][:120]}")
        print()

    # ── 8. Schema warnings ───────────────────────────────────────────
    section("8. SCHEMA WARNINGS")
    warned = [r for r in records if r.get("schema_warnings")]
    print(f"  Records with warnings: {len(warned)}")
    warn_counter = Counter(
        w for r in records for w in r.get("schema_warnings", [])
    )
    for w, cnt in warn_counter.most_common():
        print(f"    {cnt:4d}  {w}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()

    records = load(args.file)
    print(f"Loaded {len(records)} records from {args.file}")
    analyze(records)


if __name__ == "__main__":
    main()
