import pytest

from lvtest import engine
from lvtest.errors import LvtestError
from lvtest.models import Thread, Turn
from lvtest.session import load_session, save_session
from tests.conftest import NOW, PROFILE, make_session


@pytest.fixture
def resume(tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("# 김개발\n- 주문 서비스: 재고 차감에 비관적 락 적용\n", encoding="utf-8")
    return p


def test_start_creates_session(resume):
    out = engine.start(str(resume), now=NOW, session_id="s1")
    assert out["session_id"] == "s1" and out["track"] == "backend" and out["rubric_version"] == "1"
    assert "비관적 락" in out["resume_text"] and out["resume_chars"] == len(out["resume_text"])
    assert out["warnings"] == [] and out["avoid_questions"] == []
    assert [a["key"] for a in out["axes"]][:2] == ["api_design", "data_db"]
    assert set(out["axes"][0]) == {"key", "name", "description"}
    s = load_session("s1")
    assert s.state == "need_profile" and s.created_at == "2026-08-24T12:00:00+00:00"
    assert s.resume.sha256 and s.resume.path == str(resume)


def test_start_unreadable_resume(tmp_path):
    with pytest.raises(LvtestError) as ei:
        engine.start(str(tmp_path / "missing.pdf"))
    assert ei.value.code == "resume_unreadable"


def test_start_warns_on_long_resume(tmp_path):
    p = tmp_path / "long.md"
    p.write_text("x" * 8001, encoding="utf-8")
    out = engine.start(str(p), now=NOW, session_id="s2")
    assert any("8000" in w for w in out["warnings"])


def test_start_collects_avoid_questions_from_finished_sessions(resume):
    old = make_session(id="old", state="finished", finished="2026-08-01T00:00:00+00:00", threads=[
        Thread(axis="data_db", hook="h", open=False, turns=[Turn(question_no=1, stage=1, question="옛 질문", asked_at="t")]),
    ])
    save_session(old)
    unfinished = make_session(id="unf", threads=[
        Thread(axis="data_db", hook="h", turns=[Turn(question_no=1, stage=1, question="미완 질문", asked_at="t")]),
    ])
    save_session(unfinished)
    out = engine.start(str(resume), now=NOW, session_id="s3")
    assert out["avoid_questions"] == [{"axis": "data_db", "text": "옛 질문"}]
    assert load_session("s3").avoid_questions[0].text == "옛 질문"


def test_start_warns_about_unfinished_session_with_same_resume(resume):
    engine.start(str(resume), now=NOW, session_id="first")
    out = engine.start(str(resume), now=NOW, session_id="second")
    assert any("first" in w for w in out["warnings"])


def test_profile_ok(resume):
    engine.start(str(resume), now=NOW, session_id="p1")
    out = engine.profile("p1", PROFILE)
    assert out == {"ok": True, "axes_covered": [k for k in PROFILE if PROFILE[k]["hooks"]], "axes_without_hooks": ["security"]}
    s = load_session("p1")
    assert s.state == "need_question" and s.profile["data_db"].relevance == 0.9


def test_profile_missing_axis(resume):
    engine.start(str(resume), now=NOW, session_id="p2")
    data = {k: v for k, v in PROFILE.items() if k != "ops_infra"}
    with pytest.raises(LvtestError) as ei:
        engine.profile("p2", data)
    assert ei.value.code == "invalid_profile" and "ops_infra" in ei.value.extra["fields"]


def test_profile_bad_relevance(resume):
    engine.start(str(resume), now=NOW, session_id="p3")
    data = {**PROFILE, "data_db": {"relevance": 1.5, "hooks": []}}
    with pytest.raises(LvtestError) as ei:
        engine.profile("p3", data)
    assert "data_db" in ei.value.extra["fields"]


def test_profile_wrong_state(resume):
    engine.start(str(resume), now=NOW, session_id="p4")
    engine.profile("p4", PROFILE)
    with pytest.raises(LvtestError) as ei:
        engine.profile("p4", PROFILE)
    assert ei.value.code == "invalid_state"
    assert ei.value.extra == {"state": "need_question", "expected": ["need_profile"]}
