import json
from datetime import datetime, timezone

import pytest

from lvtest.errors import LvtestError
from lvtest.models import Grade, Thread, Turn
from lvtest.session import list_sessions, load_session, new_session_id, save_session, session_path
from tests.conftest import make_session


def test_new_session_id_format():
    sid = new_session_id(datetime(2026, 8, 24, 9, 5, 7, tzinfo=timezone.utc))
    assert sid.startswith("20260824-090507-")
    assert len(sid.split("-")[-1]) == 6


def test_save_and_load_roundtrip(isolated_home):
    s = make_session()
    s.threads.append(Thread(axis="data_db", hook="h", turns=[
        Turn(question_no=1, stage=1, question="Q1", asked_at="t",
             grade=Grade(axis="data_db", level_evidence=3, strength=0.8, quote="q")),
    ]))
    path = save_session(s)
    assert path == session_path(s.id) == isolated_home / "sessions" / f"{s.id}.json"
    loaded = load_session(s.id)
    assert loaded == s
    assert loaded.question_no == 1
    assert loaded.turns_for_axis("data_db")[0].grade.level_evidence == 3


def test_load_missing_raises():
    with pytest.raises(LvtestError) as ei:
        load_session("nope")
    assert ei.value.code == "session_not_found"


def test_load_corrupt_raises(isolated_home):
    p = session_path("bad")
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(LvtestError) as ei:
        load_session("bad")
    assert ei.value.code == "session_corrupt"


def test_list_sessions_skips_corrupt_and_sorts(isolated_home):
    save_session(make_session(id="b", created_at="2026-08-02T00:00:00+00:00"))
    save_session(make_session(id="a", created_at="2026-08-01T00:00:00+00:00"))
    session_path("zz").write_text("garbage", encoding="utf-8")
    assert [s.id for s in list_sessions()] == ["a", "b"]


def test_session_helpers():
    s = make_session()
    assert s.open_thread_index() is None
    assert s.last_turn() is None
    s.threads.append(Thread(axis="api_design", hook="h1", open=False, turns=[
        Turn(question_no=1, stage=1, question="Q1", asked_at="t"),
    ]))
    s.threads.append(Thread(axis="data_db", hook="h2", turns=[
        Turn(question_no=2, stage=1, question="Q2", asked_at="t"),
    ]))
    assert s.open_thread_index() == 1
    assert s.last_turn().question == "Q2"
    assert [(a.axis, a.text) for a in s.all_questions()] == [("api_design", "Q1"), ("data_db", "Q2")]
