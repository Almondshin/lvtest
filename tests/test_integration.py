"""start → profile → (next → ask → grade)* → finish 를 두 번 돌려 같은 리포트가 나오는지 본다."""
from datetime import timedelta

from lvtest import engine
from tests.conftest import NOW, PROFILE

SCRIPT = {  # axis -> 답변 시나리오 (level, strength, kind)
    "api_design": [(3, 0.8), (3, 0.7), (2, 0.6)],
    "data_db": [(4, 0.9), (4, 0.9), (4, 0.8), (3, 0.7)],
    "concurrency_perf": [(2, 0.6), (2, 0.5)],
    "architecture": [(3, 0.7), (2, 0.6)],
    "testing_quality": [(2, 0.5), (1, 0.4)],
    "ops_infra": [(3, 0.8), (3, 0.8), (3, 0.6)],
    "security": [(1, 0.5, "dont_know"), (2, 0.6), (1, 0.5)],
}


def run_session(tmp_path, sid, now):
    p = tmp_path / f"{sid}.md"
    p.write_text("# 김개발\n- 재고 차감에 비관적 락 적용\n- Redis 캐시로 응답 40% 개선\n", encoding="utf-8")
    engine.start(str(p), now=now, session_id=sid)
    engine.profile(sid, PROFILE)
    cursor = {k: 0 for k in SCRIPT}
    out = None
    while True:
        nxt = engine.next_question(sid)
        if not nxt["continue"]:
            break
        axis = nxt["axis"]
        engine.ask(sid, f"[{axis} S{nxt['stage']}] 질문 {nxt['progress']['question_no'] + 1}", now=now)
        i = cursor[axis]
        item = SCRIPT[axis][i] if i < len(SCRIPT[axis]) else (1, 0.5, "pass")
        cursor[axis] += 1
        level, strength = item[0], item[1]
        kind = item[2] if len(item) > 2 else "answered"
        out = engine.grade(sid, {"axis": axis, "level_evidence": level, "strength": strength,
                                 "answer_kind": kind, "signals": ["s"], "gaps": ["g"], "quote": "답변 인용"})
    assert out is not None and out["continue"] is False
    fin = engine.finish(sid, now=now + timedelta(minutes=40))
    fin = engine.finish(sid, summary="총평 텍스트", now=now + timedelta(minutes=41))
    return fin, open(fin["report_path"], encoding="utf-8").read()


def test_full_run_is_deterministic(tmp_path, monkeypatch):
    home_a = tmp_path / "A"
    home_b = tmp_path / "B"
    monkeypatch.setenv("LVTEST_HOME", str(home_a))
    fin_a, text_a = run_session(tmp_path, "same", NOW)
    monkeypatch.setenv("LVTEST_HOME", str(home_b))
    fin_b, text_b = run_session(tmp_path, "same", NOW)
    assert text_a == text_b
    assert {k: v for k, v in fin_a.items() if k != "report_path"} == {k: v for k, v in fin_b.items() if k != "report_path"}
    assert fin_a["end_reason"] in ("done", "max")
    assert fin_a["overall"]["level"] in (2, 3)
    assert fin_a["overall"]["bottleneck"] in ("security", "testing_quality")
    assert "## 총평\n\n총평 텍스트" in text_a and "## 부록: 전체 문답" in text_a


def test_second_run_compares_to_first(tmp_path, monkeypatch):
    monkeypatch.setenv("LVTEST_HOME", str(tmp_path / "H"))
    run_session(tmp_path, "first", NOW)
    fin, text = run_session(tmp_path, "second", NOW + timedelta(days=30))
    assert fin["comparison"]["comparable"] and fin["comparison"]["previous_id"] == "first"
    assert "## 지난 결과와 비교" in text
