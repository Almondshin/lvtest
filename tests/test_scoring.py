import pytest

from lvtest.models import Grade, Thread, Turn
from lvtest.rubric import load_rubric
from lvtest.scoring import (
    CONFIDENCE_THRESHOLD, MAX_QUESTIONS, AxisStats, compute_all, compute_axis_stats,
    compute_overall, level_from_overall, termination_reason,
)
from tests.conftest import make_session


def _thread(axis, grades, open=False):
    turns = [
        Turn(question_no=i + 1, stage=1, question=f"Q{i}", asked_at="t",
             grade=Grade(axis=axis, level_evidence=le, strength=st, quote="q"))
        for i, (le, st) in enumerate(grades)
    ]
    return Thread(axis=axis, hook="h", open=open, turns=turns)


def test_no_evidence():
    s = make_session()
    st = compute_axis_stats(s, "data_db")
    assert st == AxisStats(score=None, confidence=0.0, variance=0.0, evidence_count=0, thread_count=0)
    assert not st.asked and not st.confirmed


def test_weighted_mean_and_confidence():
    s = make_session(threads=[_thread("data_db", [(3, 0.9), (4, 0.9)])])
    st = compute_axis_stats(s, "data_db")
    assert st.score == pytest.approx(3.5)
    assert st.variance == pytest.approx(0.25)
    # min(1, 1.8/2)=0.9 ; (1 - 0.25/2)=0.875 ; 0.9*0.875=0.7875
    assert st.confidence == pytest.approx(0.7875)
    assert st.confirmed
    assert st.evidence_count == 2 and st.thread_count == 1


def test_consistent_strong_answers_confirm_quickly():
    s = make_session(threads=[_thread("api_design", [(3, 0.9), (3, 0.9)])])
    st = compute_axis_stats(s, "api_design")
    assert st.score == 3.0 and st.variance == 0.0
    assert st.confidence == pytest.approx(0.9)


def test_contradictory_answers_are_penalised():
    s = make_session(threads=[_thread("security", [(1, 1.0), (5, 1.0)])])
    st = compute_axis_stats(s, "security")
    assert st.score == 3.0 and st.variance == 4.0
    assert st.confidence == pytest.approx(0.5)  # 1.0 * (1 - 1/2)
    assert not st.confirmed


def test_zero_strength_only_is_undetermined():
    s = make_session(threads=[_thread("ops_infra", [(3, 0.0)])])
    st = compute_axis_stats(s, "ops_infra")
    assert st.score is None and st.confidence == 0.0 and st.evidence_count == 1


def test_ungraded_turns_ignored():
    th = Thread(axis="data_db", hook="h", turns=[Turn(question_no=1, stage=1, question="Q", asked_at="t")])
    s = make_session(threads=[th])
    assert compute_axis_stats(s, "data_db").evidence_count == 0


def test_compute_all_follows_rubric_order():
    r = load_rubric()
    s = make_session()
    assert list(compute_all(s, r)) == r.axis_keys


@pytest.mark.parametrize("x,level,neighbor", [
    (3.4, 3, 4), (3.6, 4, 3), (3.5, 4, 3), (3.2, 3, None), (3.75, 4, 3), (3.76, 4, None),
    (4.9, 5, None), (5.0, 5, None), (1.0, 1, None), (1.3, 1, 2), (4.7, 5, 4), (2.5, 3, 2),
])
def test_level_from_overall(x, level, neighbor):
    assert level_from_overall(x) == (level, neighbor)


def test_compute_overall():
    s = make_session(threads=[
        _thread("data_db", [(4, 1.0)]),
        _thread("security", [(2, 1.0)]),
        _thread("api_design", [(3, 1.0)]),
    ])
    stats = compute_all(s, load_rubric())
    o = compute_overall(stats)
    assert o.score == 3.0 and o.level == 3 and o.neighbor is None
    assert o.bottleneck == "security"
    assert o.undetermined == ["concurrency_perf", "architecture", "testing_quality", "ops_infra"]


def test_compute_overall_empty():
    o = compute_overall(compute_all(make_session(), load_rubric()))
    assert o.score is None and o.level is None and o.bottleneck is None and len(o.undetermined) == 7


def test_termination_done_when_all_confirmed():
    r = load_rubric()
    s = make_session(threads=[_thread(k, [(3, 0.9), (3, 0.9)]) for k in r.axis_keys])
    assert termination_reason(s, compute_all(s, r)) == "done"


def test_termination_not_done_if_one_axis_unasked():
    r = load_rubric()
    s = make_session(threads=[_thread(k, [(3, 0.9), (3, 0.9)]) for k in r.axis_keys[:-1]])
    assert termination_reason(s, compute_all(s, r)) is None


def test_termination_max():
    r = load_rubric()
    grades = [(1, 0.1)] * MAX_QUESTIONS
    s = make_session(threads=[_thread("data_db", grades)])
    assert termination_reason(s, compute_all(s, r)) == "max"


def test_bottleneck_ignores_float_noise_and_breaks_ties_by_rubric_order():
    # 3 grades: 8.1/2.7 = 3.0000000000000004 ; 2 grades: 5.4/1.8 = 3.0 exactly
    s = make_session(threads=[
        _thread("api_design", [(3, 0.9), (3, 0.9), (3, 0.9)]),
        _thread("security", [(3, 0.9), (3, 0.9)]),
    ])
    stats = compute_all(s, load_rubric())
    assert stats["api_design"].score != stats["security"].score  # raw floats differ
    assert compute_overall(stats).bottleneck == "api_design"      # rounded tie → rubric order
