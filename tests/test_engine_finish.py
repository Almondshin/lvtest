from datetime import timedelta

import pytest

from lvtest import engine
from lvtest.errors import LvtestError
from lvtest.report import load_index
from lvtest.session import load_session
from tests.conftest import NOW, PROFILE


def _start(tmp_path, sid, now=NOW):
    p = tmp_path / "resume.md"
    p.write_text("# 김개발\n- 재고 차감에 비관적 락 적용\n", encoding="utf-8")
    engine.start(str(p), now=now, session_id=sid)
    engine.profile(sid, PROFILE)
    return sid


def _answer(sid, level, strength=0.9):
    nxt = engine.next_question(sid)
    engine.ask(sid, f"Q {nxt['axis']} S{nxt['stage']}", now=NOW)
    return engine.grade(sid, {"axis": nxt["axis"], "level_evidence": level, "strength": strength, "quote": "인용"})


def _run_to_done(sid, level=3):
    out = None
    while out is None or out["continue"]:
        out = _answer(sid, level)   # stage1 pass, stage2 pass(3>=3), stage3 fail -> 3 per axis
    return out


def test_finish_after_done(tmp_path, isolated_home):
    sid = _start(tmp_path, "f1")
    assert _run_to_done(sid)["reason"] == "done"
    out = engine.finish(sid, now=NOW + timedelta(minutes=30))
    assert out["end_reason"] == "done" and out["has_summary"] is False
    assert out["overall"] == {"score": 3.0, "level": 3, "level_name": "미드", "neighbor": None, "bottleneck": "api_design", "undetermined": []}
    assert out["axes"]["data_db"]["score"] == 3.0 and out["axes"]["data_db"]["confidence"] > 0.7
    assert out["comparison"] is None
    path = isolated_home / "reports" / "2026-08-24-f1.md"
    assert out["report_path"] == str(path) and path.read_text(encoding="utf-8").startswith("# 백엔드 레벨테스트 결과")
    s = load_session(sid)
    assert s.state == "finished" and s.finished == "2026-08-24T12:30:00+00:00"
    assert load_index()[0]["id"] == "f1"
    assert engine.status(sid)["report_path"] == str(path)


def test_finish_with_summary_is_idempotent(tmp_path, isolated_home):
    sid = _start(tmp_path, "f2")
    _run_to_done(sid)
    first = engine.finish(sid, now=NOW)
    second = engine.finish(sid, summary="총평입니다.", now=NOW + timedelta(days=1))
    assert second["report_path"] == first["report_path"] and second["has_summary"] is True
    assert "## 총평\n\n총평입니다." in (isolated_home / "reports" / "2026-08-24-f2.md").read_text(encoding="utf-8")
    assert load_session(sid).finished == "2026-08-24T12:00:00+00:00"  # first finish time kept
    assert len(load_index()) == 1


def test_finish_user_stop_mid_answer(tmp_path):
    sid = _start(tmp_path, "f3")
    _answer(sid, 3)
    engine.ask(sid, "답 안 한 질문")
    out = engine.finish(sid)
    assert out["end_reason"] == "user_stop"
    assert out["overall"]["undetermined"] and "data_db" not in out["overall"]["undetermined"]
    assert "(미응답)" in open(out["report_path"], encoding="utf-8").read()


def test_finish_explicit_reason_validation(tmp_path):
    sid = _start(tmp_path, "f4")
    with pytest.raises(LvtestError) as ei:
        engine.finish(sid, reason="bored")
    assert ei.value.code == "invalid_reason"


def test_finish_wrong_state(tmp_path):
    p = tmp_path / "r.md"
    p.write_text("x", encoding="utf-8")
    engine.start(str(p), session_id="f5")
    with pytest.raises(LvtestError) as ei:
        engine.finish("f5")
    assert ei.value.code == "invalid_state"


def test_second_session_gets_comparison_and_avoid(tmp_path):
    a = _start(tmp_path, "a", now=NOW)
    _run_to_done(a, level=2)   # stage1 pass(2>=2), stage2 fail -> 2 per axis, score 2.0
    engine.finish(a, now=NOW)
    b = _start(tmp_path, "b", now=NOW + timedelta(days=7))
    first = engine.next_question(b)
    assert first["avoid"] == ["Q data_db S1", "Q data_db S2"]
    _run_to_done(b, level=3)
    out = engine.finish(b, now=NOW + timedelta(days=7))
    assert out["comparison"]["comparable"] and out["comparison"]["previous_id"] == "a"
    assert out["comparison"]["overall"] == {"prev": 2.0, "now": 3.0, "delta": 1.0}


def test_history_and_sessions(tmp_path):
    a = _start(tmp_path, "h1", now=NOW)
    _run_to_done(a)
    engine.finish(a, now=NOW)
    _start(tmp_path, "h2", now=NOW + timedelta(days=1))
    hist = engine.history()
    assert [e["id"] for e in hist["sessions"]] == ["h1"]
    assert {"id", "date", "overall", "level", "rubric_version", "report_path", "end_reason"} <= set(hist["sessions"][0])
    live = engine.sessions()
    assert [s["id"] for s in live["sessions"]] == ["h2"]
    assert live["sessions"][0]["state"] == "need_question" and live["sessions"][0]["question_no"] == 0
