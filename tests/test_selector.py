from lvtest.models import Grade, ProfileAxis, Thread, Turn
from lvtest.rubric import load_rubric
from lvtest.scoring import compute_all
from lvtest.selector import Choice, choose_next, pick_hook
from tests.conftest import PROFILE, make_session

R = load_rubric()


def _thread(axis, grades, open=False, hook="h", stage=1):
    turns = [
        Turn(question_no=i + 1, stage=1, question=f"Q{i}", asked_at="t",
             grade=Grade(axis=axis, level_evidence=le, strength=st, quote="q"))
        for i, (le, st) in enumerate(grades)
    ]
    return Thread(axis=axis, hook=hook, open=open, stage=stage, turns=turns)


def _choose(s):
    return choose_next(s, R, compute_all(s, R))


def test_first_question_is_unasked_axis_with_highest_relevance():
    s = make_session()
    c = _choose(s)
    assert c == Choice(axis="data_db", thread_idx=None, stage=1, hook="재고 차감에 비관적 락 적용")


def test_open_thread_always_continues():
    s = make_session(threads=[_thread("security", [(3, 0.9)], open=True, hook="hk", stage=2)])
    assert _choose(s) == Choice(axis="security", thread_idx=0, stage=2, hook="hk")


def test_unasked_axes_before_low_confidence_ones():
    # data_db asked once with weak evidence -> still unconfirmed, but api_design never asked
    s = make_session(threads=[_thread("data_db", [(2, 0.3)])])
    assert _choose(s).axis == "concurrency_perf"  # next-highest relevance among unasked


def test_relevance_tie_breaks_by_rubric_order():
    prof = {k: ProfileAxis(relevance=0.5, hooks=["h"]) for k in R.axis_keys}
    s = make_session(profile=prof)
    assert _choose(s).axis == "api_design"


def test_priority_formula_when_all_asked():
    threads = [_thread(k, [(3, 0.9), (3, 0.9)]) for k in R.axis_keys]  # all confirmed (0.9)
    threads[1] = _thread("data_db", [(3, 0.4)], hook="재고 차감에 비관적 락 적용")  # conf 0.2, rel 0.9 -> 0.8*0.95=0.76
    threads[6] = _thread("security", [(3, 0.2)])           # conf 0.1, relevance 0.1 -> 0.9*0.55=0.495
    s = make_session(threads=threads)
    c = _choose(s)
    assert c.axis == "data_db" and c.thread_idx is None and c.stage == 1
    assert c.hook == "PostgreSQL 마이그레이션 주도"  # second hook, first already used


def test_confirmed_axes_are_excluded():
    threads = [_thread(k, [(3, 0.9), (3, 0.9)]) for k in R.axis_keys]
    s = make_session(threads=threads)
    assert _choose(s) is None


def test_thread_cap_excludes_axis():
    threads = [_thread(k, [(3, 0.9), (3, 0.9)]) for k in R.axis_keys]
    threads[1] = _thread("data_db", [(3, 0.2)])
    threads.append(_thread("data_db", [(3, 0.2)]))  # second thread, still unconfirmed
    s = make_session(threads=threads)
    assert _choose(s) is None


def test_pick_hook_reuses_first_when_all_used_or_empty():
    s = make_session(threads=[_thread("api_design", [(3, 0.5)], hook="주문 API를 REST로 설계")])
    assert pick_hook(s, "api_design") == "주문 API를 REST로 설계"
    assert pick_hook(s, "security") == ""


def test_works_without_profile():
    s = make_session(profile=None)
    assert _choose(s) == Choice(axis="api_design", thread_idx=None, stage=1, hook="")
