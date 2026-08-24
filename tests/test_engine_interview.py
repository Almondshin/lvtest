import pytest

from lvtest import engine
from lvtest.errors import LvtestError
from lvtest.scoring import MAX_QUESTIONS
from lvtest.session import load_session
from tests.conftest import NOW, PROFILE


@pytest.fixture
def sid(tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("# 김개발\n- 재고 차감에 비관적 락 적용\n", encoding="utf-8")
    engine.start(str(p), now=NOW, session_id="iv")
    engine.profile("iv", PROFILE)
    return "iv"


def _grade(level, strength=0.9, kind="answered"):
    return {"axis": None, "level_evidence": level, "strength": strength, "answer_kind": kind,
            "signals": ["s"], "gaps": [], "quote": "인용"}


def _answer(sid, level, strength=0.9, kind="answered"):
    nxt = engine.next_question(sid)
    engine.ask(sid, f"Q about {nxt['axis']} stage {nxt['stage']}", now=NOW)
    return engine.grade(sid, {**_grade(level, strength, kind), "axis": nxt["axis"]})


def test_next_first_question_payload(sid):
    out = engine.next_question(sid)
    assert out["continue"] is True
    assert out["axis"] == "data_db" and out["axis_name"] == "데이터 모델링·DB·트랜잭션"
    assert out["stage"] == 1 and out["pass_level"] == 2 and out["stage_goal"].startswith("경험 확인")
    assert set(out["anchors"]) == {"1", "2", "3", "4", "5"}
    assert "probe_guide" in out and out["hook"] == "재고 차감에 비관적 락 적용"
    assert out["hooks"] == PROFILE["data_db"]["hooks"] and out["thread"] == [] and out["avoid"] == []
    assert out["progress"] == {"question_no": 0, "max_questions": MAX_QUESTIONS, "axes_confirmed": 0, "axes_total": 7}


def test_next_is_pure(sid):
    engine.next_question(sid)
    engine.next_question(sid)
    assert load_session(sid).threads == [] and load_session(sid).state == "need_question"


def test_ask_opens_thread_and_sets_state(sid):
    out = engine.ask(sid, "첫 질문", now=NOW)
    assert out == {"ok": True, "question_no": 1, "axis": "data_db", "stage": 1}
    s = load_session(sid)
    assert s.state == "awaiting_answer"
    assert len(s.threads) == 1 and s.threads[0].open and s.threads[0].turns[0].question == "첫 질문"
    assert s.threads[0].turns[0].asked_at == "2026-08-24T12:00:00+00:00"


def test_ask_rejects_blank(sid):
    with pytest.raises(LvtestError) as ei:
        engine.ask(sid, "   ")
    assert ei.value.code == "invalid_question"


def test_ask_wrong_state(sid):
    engine.ask(sid, "Q")
    with pytest.raises(LvtestError) as ei:
        engine.ask(sid, "Q2")
    assert ei.value.code == "invalid_state"


def test_grade_pass_continues_thread_with_next_stage(sid):
    out = _answer(sid, level=3)
    assert out["ok"] and out["continue"] and out["reason"] is None and out["thread_status"] == "continue"
    assert out["progress"]["question_no"] == 1
    s = load_session(sid)
    assert s.state == "need_question" and s.threads[0].open and s.threads[0].stage == 2
    nxt = engine.next_question(sid)
    assert nxt["axis"] == "data_db" and nxt["stage"] == 2 and nxt["pass_level"] == 3
    assert nxt["thread"] == [{"question": "Q about data_db stage 1", "stage": 1, "level_evidence": 3, "quote": "인용"}]


def test_grade_fail_closes_thread_and_moves_on(sid):
    out = _answer(sid, level=1)
    assert out["thread_status"] == "closed"
    s = load_session(sid)
    assert not s.threads[0].open and s.threads[0].stage == 1
    assert engine.next_question(sid)["axis"] == "concurrency_perf"


def test_grade_dont_know_closes_thread(sid):
    out = _answer(sid, level=5, kind="dont_know")
    assert out["thread_status"] == "closed"
    g = load_session(sid).threads[0].turns[0].grade
    assert g.level_evidence == 1 and g.strength == 0.5 and g.answer_kind == "dont_know"


def test_stage_four_pass_closes_thread(sid):
    for level in (3, 4, 5, 5):
        out = _answer(sid, level=level)
    assert out["thread_status"] == "closed"
    s = load_session(sid)
    assert not s.threads[0].open and s.threads[0].stage == 4 and len(s.threads[0].turns) == 4


def test_grade_invalid_keeps_state(sid):
    engine.ask(sid, "Q")
    with pytest.raises(LvtestError) as ei:
        engine.grade(sid, {"axis": "data_db", "level_evidence": 9, "strength": 0.5, "quote": "x"})
    assert ei.value.code == "invalid_grade"
    assert load_session(sid).state == "awaiting_answer"


def test_grade_wrong_axis_rejected(sid):
    engine.ask(sid, "Q")
    with pytest.raises(LvtestError) as ei:
        engine.grade(sid, {**_grade(3), "axis": "security"})
    assert "axis" in ei.value.extra["fields"]


def test_grade_ungradable(sid):
    engine.ask(sid, "Q")
    out = engine.grade_ungradable(sid)
    assert out["thread_status"] == "closed"
    g = load_session(sid).threads[0].turns[0].grade
    assert g.answer_kind == "ungradable" and g.strength == 0.3 and g.level_evidence == 1


def test_full_confirmation_ends_with_done(sid):
    # two strong consistent answers per axis; first passes stage1 (>=2), second fails stage2 (<3) -> thread closes
    for _ in range(7):
        _answer(sid, level=2)
        out = _answer(sid, level=2)
    assert out["continue"] is False and out["reason"] == "done"
    s = load_session(sid)
    assert s.state == "need_finish" and s.end_reason == "done"
    assert engine.next_question(sid) == {"continue": False, "reason": "done", "progress": out["progress"]}
    with pytest.raises(LvtestError) as ei:
        engine.ask(sid, "one more")
    assert ei.value.code == "invalid_state"


def test_max_questions_ends_with_max(sid):
    # level 5 keeps every thread open for 4 stages; strength 0.1 keeps every axis unconfirmed
    # (7 axes x 4 questions = 28 > 25), so the cap is what ends it.
    out = None
    for _ in range(MAX_QUESTIONS):
        out = _answer(sid, level=5, strength=0.1)
    assert out["continue"] is False and out["reason"] == "max"
    assert load_session(sid).end_reason == "max"


def test_status_reports_next_action(sid):
    st = engine.status(sid)
    assert st["state"] == "need_question" and "lvtest next" in st["next_action"] and st["last_question"] is None
    engine.ask(sid, "질문 1")
    st = engine.status(sid)
    assert st["state"] == "awaiting_answer" and st["last_question"] == "질문 1" and st["last_question_axis"] == "data_db"
    assert "lvtest grade" in st["next_action"]
    assert st["progress"]["question_no"] == 1
    assert st["session_summary"]["axes"]["data_db"] == {"score": None, "confidence": 0.0, "threads": 1}


def test_status_missing_session():
    with pytest.raises(LvtestError) as ei:
        engine.status("nope")
    assert ei.value.code == "session_not_found"
