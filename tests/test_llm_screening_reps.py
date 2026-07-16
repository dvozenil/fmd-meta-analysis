"""Unit tests for the repeated-questioning consensus logic in llm_screen_abstracts.

Covers `_decision_order` and the consensus aggregation in `call_model_with_reps`
(majority vote, tie-breaking toward inclusivity, confidence denominator, the
all-failed path, and primary-run selection). `call_model` is mocked so no API
calls are made; only the aggregation logic is exercised.

Run standalone:  python tests/test_llm_screening_reps.py
Or with pytest:  pytest tests/test_llm_screening_reps.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Allow running from repo root without installation.
# scripts/ has no __init__.py, so add it to sys.path and import by name.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import llm_screen_abstracts as scr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(decision=None, error=None, source="pubmed", tag=None):
    """Build a fake `call_model` return dict.

    `decision` None models a failed run (no llm_decision). `tag` is embedded in
    the llm_decision so tests can identify which run became the primary.
    """
    r = {
        "record_id": "R1",
        "source": source,
        "input_record": {"record_id": "R1"},
        "llm_decision": None,
        "schema_warnings": [],
        "raw_response": None,
    }
    if decision is not None:
        llm = {"decision": decision}
        if tag is not None:
            llm["tag"] = tag
        r["llm_decision"] = llm
    if error is not None:
        r["error"] = error
    return r


def _run(results):
    """Call call_model_with_reps with call_model mocked to yield `results` in order.

    reps == len(results). Returns (output, mock) so call counts can be checked.
    """
    record = {"record_id": "R1"}
    # Copy each result so the _rep mutation inside call_model_with_reps cannot
    # leak across runs when the same template is reused by a caller.
    seq = [dict(r) for r in results]
    with patch.object(scr, "call_model", side_effect=seq) as m:
        out = scr.call_model_with_reps(
            record=record,
            base_url="http://example",
            api_key="key",
            model="m",
            temperature=0.0,
            timeout=120,
            max_retries=3,
            use_response_format=True,
            reps=len(results),
            thinking=None,
            system_prompt=None,
        )
    return out, m


# ---------------------------------------------------------------------------
# _decision_order
# ---------------------------------------------------------------------------

def test_decision_order_ranking():
    """include_candidate > unclear > exclude; unknown decisions sort lowest.

    NOTE: the source docstring says 'include_candidate > exclude > unclear',
    but the implementation's order dict ranks unclear above exclude. These
    asserts pin the actual (correct) behavior.
    """
    assert scr._decision_order("include_candidate") == 2
    assert scr._decision_order("unclear") == 1
    assert scr._decision_order("exclude") == 0
    assert scr._decision_order("nonsense") == -1
    assert scr._decision_order("") == -1
    print("✓ _decision_order: include(2) > unclear(1) > exclude(0) > unknown(-1)")


# ---------------------------------------------------------------------------
# Majority vote
# ---------------------------------------------------------------------------

def test_unanimous():
    out, m = _run([_result("include_candidate"),
                   _result("include_candidate"),
                   _result("include_candidate")])
    assert out["consensus_decision"] == "include_candidate"
    assert out["consensus_confidence"] == 1.0
    assert out["consensus_counts"] == {"include_candidate": 3}
    assert out["failed_runs"] == 0
    assert m.call_count == 3
    print("✓ unanimous: 3/3 include → consensus=include_candidate, conf=1.0")


def test_majority_vote():
    out, _ = _run([_result("include_candidate"),
                  _result("exclude"),
                  _result("include_candidate")])
    assert out["consensus_decision"] == "include_candidate"
    assert out["consensus_confidence"] == 2 / 3
    assert out["consensus_counts"] == {"include_candidate": 2, "exclude": 1}
    print("✓ majority: 2 include + 1 exclude → include_candidate, conf=2/3")


# ---------------------------------------------------------------------------
# Tie-breaking toward inclusivity
# ---------------------------------------------------------------------------

def test_tie_include_beats_exclude():
    out, _ = _run([_result("include_candidate"),
                  _result("include_candidate"),
                  _result("exclude"),
                  _result("exclude")])
    assert out["consensus_decision"] == "include_candidate"  # tie → most inclusive
    assert out["consensus_confidence"] == 0.5
    print("✓ tie include vs exclude → include_candidate wins (most inclusive)")


def test_tie_unclear_beats_exclude():
    out, _ = _run([_result("unclear"), _result("exclude")])
    assert out["consensus_decision"] == "unclear"  # unclear > exclude
    assert out["consensus_confidence"] == 0.5
    print("✓ tie unclear vs exclude → unclear wins (unclear > exclude)")


def test_three_way_tie_include_wins():
    out, _ = _run([_result("include_candidate"),
                  _result("unclear"),
                  _result("exclude")])
    # All tied at 1 → most inclusive (include_candidate) wins
    assert out["consensus_decision"] == "include_candidate"
    assert out["consensus_confidence"] == 1 / 3
    print("✓ three-way tie → include_candidate wins (most inclusive)")


# ---------------------------------------------------------------------------
# Confidence denominator and failure handling
# ---------------------------------------------------------------------------

def test_confidence_denominator_is_total_reps():
    # 2 successes + 1 failure. Confidence must be 2/3 (over total reps),
    # NOT 2/2 = 1.0 (over successes only).
    out, _ = _run([_result("include_candidate"),
                  _result("include_candidate"),
                  _result(error="timeout")])
    assert out["consensus_decision"] == "include_candidate"
    assert out["consensus_confidence"] == 2 / 3
    assert out["failed_runs"] == 1
    print("✓ confidence uses total reps (2/3, not 1.0) when a run fails")


def test_all_failed():
    out, _ = _run([_result(error="err1"), _result(error="err2"), _result(error="err3")])
    assert out["consensus_decision"] is None
    assert out["consensus_confidence"] == 0.0
    assert out["consensus_counts"] == {}
    assert out["failed_runs"] == 3
    assert out["llm_decision"] is None
    # Error from the last run is carried through
    assert out["error"] == "err3"
    print("✓ all failed → consensus=None, conf=0.0, failed_runs=3, last error carried")


# ---------------------------------------------------------------------------
# Primary-run selection and run bookkeeping
# ---------------------------------------------------------------------------

def test_primary_is_first_run_matching_consensus():
    # rep1 exclude, rep2 include, rep3 include → consensus=include,
    # primary should be rep2 (first include), not rep3.
    out, _ = _run([_result("exclude", tag="rep1"),
                  _result("include_candidate", tag="rep2"),
                  _result("include_candidate", tag="rep3")])
    assert out["consensus_decision"] == "include_candidate"
    assert out["llm_decision"]["tag"] == "rep2"
    print("✓ primary = first run matching consensus (rep2, not rep3)")


def test_individual_runs_tagged_with_rep():
    out, m = _run([_result("include_candidate"),
                  _result("exclude"),
                  _result("unclear")])
    assert m.call_count == 3
    assert len(out["individual_runs"]) == 3
    assert [r["_rep"] for r in out["individual_runs"]] == [1, 2, 3]
    print("✓ call_model invoked 3x; individual_runs tagged _rep=1,2,3")


def test_single_rep_no_overhead():
    # reps=1 is the documented "no repeats" case at the consensus layer:
    # still returns a valid consensus == the single run's decision.
    out, _ = _run([_result("exclude")])
    assert out["consensus_decision"] == "exclude"
    assert out["consensus_confidence"] == 1.0
    assert out["failed_runs"] == 0
    print("✓ reps=1 → consensus == single decision, conf=1.0")


if __name__ == "__main__":
    test_decision_order_ranking()
    test_unanimous()
    test_majority_vote()
    test_tie_include_beats_exclude()
    test_tie_unclear_beats_exclude()
    test_three_way_tie_include_wins()
    test_confidence_denominator_is_total_reps()
    test_all_failed()
    test_primary_is_first_run_matching_consensus()
    test_individual_runs_tagged_with_rep()
    test_single_rep_no_overhead()
    print("\n=== All tests passed! ===")
