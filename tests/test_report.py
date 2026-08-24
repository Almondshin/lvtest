from lvtest.models import Grade, Thread, Turn
from lvtest.report import (
    build_comparison, index_entry, load_index, previous_entry, render_report, report_filename, upsert_index,
)
from lvtest.rubric import load_rubric
from lvtest.scoring import compute_all, compute_overall
from tests.conftest import make_session

R = load_rubric()


def _thread(axis, grades, hook="h", open=False):
    turns = [
        Turn(question_no=i + 1, stage=i + 1, question=f"{axis} 질문 {i + 1}", asked_at="t",
             grade=Grade(axis=axis, level_evidence=le, strength=st, quote=f"{axis} 인용 {i + 1}",
                         signals=[f"{axis} 시그널"], gaps=[f"{axis} 갭"]))
        for i, (le, st) in enumerate(grades)
    ]
    return Thread(axis=axis, hook=hook, open=open, turns=turns)


def _finished_session(**kw):
    threads = [_thread(k, [(3, 0.9), (3, 0.9)]) for k in R.axis_keys]
    threads[1] = _thread("data_db", [(4, 0.9), (4, 0.9)])
    threads[6] = _thread("security", [(2, 0.9), (2, 0.9)])
    base = dict(threads=threads, state="finished", end_reason="done", finished="2026-08-24T12:30:00+00:00")
    base.update(kw)
    return make_session(**base)


def test_filename():
    assert report_filename(make_session()) == "2026-08-24-20260824-120000-abc123.md"


def test_render_sections_and_numbers():
    s = _finished_session(summary="전체적으로 탄탄합니다.")
    stats = compute_all(s, R)
    text = render_report(s, R, stats, compute_overall(stats), None)
    assert text.startswith("# 백엔드 레벨테스트 결과 — 2026-08-24")
    assert "## 종합: L3 미드" in text and "평균 3.0" in text
    assert "병목: 보안·인증 2.0" in text
    assert "종료 사유: 확신도 충족 (14문항) · 루브릭 v1" in text
    assert "| 데이터 모델링·DB·트랜잭션 | 4.0 | 0.90 | data_db 인용 1 | data_db 갭 |" in text
    assert "## 강점" in text and "## 약점" in text
    assert "## 다음 레벨로 가려면" in text
    assert "### 보안·인증: L2 → L3" in text
    assert "인증과 인가를 구분하고" in text  # security L3 anchor quoted from rubric
    assert "## 지난 결과와 비교" not in text
    assert "## 총평\n\n전체적으로 탄탄합니다." in text
    assert "## 부록: 전체 문답" in text and "**Q1 (S1)** api_design 질문 1" in text


def test_render_marks_undetermined_and_unanswered():
    s = make_session(state="finished", end_reason="user_stop", finished="t", threads=[
        _thread("data_db", [(3, 0.9)], open=True),
    ])
    s.threads[0].turns.append(Turn(question_no=2, stage=2, question="미응답 질문", asked_at="t"))
    stats = compute_all(s, R)
    text = render_report(s, R, stats, compute_overall(stats), None)
    assert "종료 사유: 사용자 중단" in text
    assert "미확정 축" in text and "API·서비스 설계" in text
    assert "| API·서비스 설계 | — | 0.00 | — | — |" in text
    assert "(미응답)" in text


def test_render_dont_know_turn():
    s = make_session(state="finished", end_reason="done", finished="t", threads=[
        Thread(axis="security", hook="h", open=False, turns=[
            Turn(question_no=1, stage=1, question="Q", asked_at="t",
                 grade=Grade(axis="security", level_evidence=1, strength=0.5, answer_kind="dont_know")),
        ]),
    ])
    stats = compute_all(s, R)
    text = render_report(s, R, stats, compute_overall(stats), None)
    assert "(모르겠다)" in text


def test_index_roundtrip_and_previous(isolated_home):
    assert load_index() == []
    a = _finished_session(id="a", created_at="2026-08-01T00:00:00+00:00")
    b = _finished_session(id="b", created_at="2026-08-02T00:00:00+00:00")
    index = load_index()
    for s in (b, a):
        stats = compute_all(s, R)
        upsert_index(index, index_entry(s, stats, compute_overall(stats), isolated_home / "reports" / report_filename(s)))
    assert [e["id"] for e in load_index()] == ["a", "b"]
    upsert_index(index, {**index[0], "overall": 9.9})
    assert len(load_index()) == 2 and load_index()[0]["overall"] == 9.9
    assert previous_entry(load_index(), b)["id"] == "a"
    assert previous_entry(load_index(), a) is None
    other = _finished_session(id="c", created_at="2026-08-03T00:00:00+00:00", track="frontend")
    assert previous_entry(load_index(), other) is None


def test_comparison_deltas():
    prev = _finished_session(id="p", created_at="2026-08-01T00:00:00+00:00")
    pstats = compute_all(prev, R)
    pentry = index_entry(prev, pstats, compute_overall(pstats), "x.md")
    now = _finished_session(id="n")
    now.threads[6] = _thread("security", [(3, 0.9), (3, 0.9)])
    nstats = compute_all(now, R)
    c = build_comparison(pentry, nstats, compute_overall(nstats), now)
    assert c["comparable"] is True and c["previous_id"] == "p"
    assert c["axes"]["security"] == {"prev": 2.0, "now": 3.0, "delta": 1.0}
    assert c["overall"]["delta"] == round(c["overall"]["now"] - c["overall"]["prev"], 2)
    text = render_report(now, R, nstats, compute_overall(nstats), c)
    assert "## 지난 결과와 비교" in text and "| 보안·인증 | 2.0 | 3.0 | +1.0 |" in text


def test_comparison_rubric_mismatch():
    prev = _finished_session(id="p", created_at="2026-08-01T00:00:00+00:00", rubric_version="0")
    pstats = compute_all(prev, R)
    pentry = index_entry(prev, pstats, compute_overall(pstats), "x.md")
    now = _finished_session(id="n")
    nstats = compute_all(now, R)
    c = build_comparison(pentry, nstats, compute_overall(nstats), now)
    assert c["comparable"] is False and "루브릭" in c["reason"]
    text = render_report(now, R, nstats, compute_overall(nstats), c)
    assert "루브릭 변경으로 비교 불가" in text
