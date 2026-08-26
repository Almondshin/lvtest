"""트랙(backend / devops) 선택 — 별칭 해석, 데브옵스 루브릭, 트랙별 리포트."""
import pytest

from lvtest import engine
from lvtest.errors import LvtestError
from lvtest.report import render_report
from lvtest.rubric import DEVOPS_AXIS_KEYS, available_tracks, load_rubric, resolve_track
from lvtest.scoring import compute_all, compute_overall
from lvtest.session import load_session
from tests.conftest import DEVOPS_PROFILE, NOW, make_session


# ---------- 트랙 해석 ----------

@pytest.mark.parametrize(
    "given,expected",
    [
        (None, "backend"),
        ("be", "backend"),
        ("backend", "backend"),
        ("BE", "backend"),
        ("  devops  ", "devops"),
        ("devops", "devops"),
        ("ops", "devops"),
        ("infra", "devops"),
    ],
)
def test_resolve_track_accepts_aliases(given, expected):
    assert resolve_track(given) == expected


def test_resolve_track_rejects_unknown_and_lists_available():
    with pytest.raises(LvtestError) as ei:
        resolve_track("frontend")
    assert ei.value.code == "unknown_track"
    assert ei.value.extra["track"] == "frontend"
    assert ei.value.extra["available"] == ["backend", "devops"]


def test_available_tracks():
    assert available_tracks() == ["backend", "devops"]


# ---------- 데브옵스 루브릭 ----------

def test_devops_rubric_loads_with_seven_axes():
    r = load_rubric("devops")
    assert r.track == "devops"
    assert r.label == "데브옵스"
    assert r.axis_keys == DEVOPS_AXIS_KEYS == [
        "iac_provisioning", "cicd_delivery", "container_orchestration",
        "observability_incident", "reliability_scaling", "network_infra", "security_compliance",
    ]
    assert r.levels[3] == "미드"
    assert {s: r.stages[s].pass_level for s in (1, 2, 3, 4)} == {1: 2, 2: 3, 3: 4, 4: 5}


def test_devops_rubric_every_axis_is_complete():
    r = load_rubric("devops")
    for axis in r.axes:
        assert axis.name and axis.description
        assert set(axis.levels) == {1, 2, 3, 4, 5}
        assert all(axis.levels[level] for level in axis.levels)
        assert set(axis.probes) == {1, 2, 3, 4}
        assert all(axis.probes[stage].strip() for stage in axis.probes)


def test_backend_rubric_has_label():
    assert load_rubric("backend").label == "백엔드"


def test_devops_rubric_loads_through_alias():
    assert load_rubric("infra").track == "devops"


# ---------- 세션 ----------

@pytest.fixture
def resume(tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("# 우데브옵스\n- Terraform으로 EKS 클러스터 프로비저닝\n", encoding="utf-8")
    return p


def test_start_normalizes_alias_to_canonical_track(resume):
    out = engine.start(str(resume), track="be", now=NOW, session_id="t1")
    assert out["track"] == "backend"
    assert load_session("t1").track == "backend"


def test_start_with_devops_track_returns_devops_axes(resume):
    out = engine.start(str(resume), track="devops", now=NOW, session_id="t2")
    assert out["track"] == "devops"
    assert [a["key"] for a in out["axes"]] == DEVOPS_AXIS_KEYS
    assert load_session("t2").track == "devops"


def test_start_rejects_unknown_track(resume):
    with pytest.raises(LvtestError) as ei:
        engine.start(str(resume), track="frontend", now=NOW, session_id="t3")
    assert ei.value.code == "unknown_track"


def test_unfinished_session_warning_names_the_track(resume):
    engine.start(str(resume), track="devops", now=NOW, session_id="earlier")
    out = engine.start(str(resume), track="devops", now=NOW, session_id="later")
    assert any("earlier" in w and "devops" in w for w in out["warnings"])


def test_profile_accepts_devops_axes(resume):
    engine.start(str(resume), track="devops", now=NOW, session_id="t4")
    out = engine.profile("t4", DEVOPS_PROFILE)
    assert out["ok"] is True
    assert out["axes_without_hooks"] == ["security_compliance"]


def test_profile_rejects_backend_axes_on_devops_track(resume):
    from tests.conftest import PROFILE

    engine.start(str(resume), track="devops", now=NOW, session_id="t5")
    with pytest.raises(LvtestError) as ei:
        engine.profile("t5", PROFILE)
    assert ei.value.code == "invalid_profile"
    assert set(ei.value.extra["fields"]) == set(DEVOPS_AXIS_KEYS)


def test_next_question_uses_devops_rubric(resume):
    engine.start(str(resume), track="devops", now=NOW, session_id="t6")
    engine.profile("t6", DEVOPS_PROFILE)
    nxt = engine.next_question("t6")
    assert nxt["axis"] in DEVOPS_AXIS_KEYS
    assert nxt["progress"]["axes_total"] == 7


# ---------- 리포트 ----------

def test_report_title_follows_the_track():
    r = load_rubric("devops")
    s = make_session(track="devops", state="finished", end_reason="user_stop", finished="t")
    stats = compute_all(s, r)
    text = render_report(s, r, stats, compute_overall(stats), None)
    assert text.startswith("# 데브옵스 레벨테스트 결과 — 2026-08-24")


# ---------- 트랙 격리 ----------

def test_avoid_questions_do_not_leak_across_tracks(resume):
    from lvtest.models import Thread, Turn
    from lvtest.session import save_session

    finished_backend = make_session(
        id="be-done", track="backend", state="finished", finished="2026-08-01T00:00:00+00:00",
        threads=[Thread(axis="data_db", hook="h", open=False,
                        turns=[Turn(question_no=1, stage=1, question="백엔드 옛 질문", asked_at="t")])],
    )
    save_session(finished_backend)
    out = engine.start(str(resume), track="devops", now=NOW, session_id="fresh-devops")
    assert out["avoid_questions"] == []


# ---------- 트랙 목록 ----------

def test_engine_tracks_lists_each_track_with_its_axes():
    out = engine.tracks()
    assert [t["track"] for t in out["tracks"]] == ["backend", "devops"]
    backend, devops = out["tracks"]
    assert backend["label"] == "백엔드"
    assert backend["aliases"] == ["backend", "be", "server"]
    assert [a["key"] for a in devops["axes"]] == DEVOPS_AXIS_KEYS
    assert devops["aliases"] == ["devops", "infra", "ops", "sre"]
    assert devops["rubric_version"] == "1"


def test_tracks_command_emits_json():
    import json

    from typer.testing import CliRunner

    from lvtest.cli import app

    result = CliRunner().invoke(app, ["tracks"])
    assert result.exit_code == 0
    assert [t["track"] for t in json.loads(result.stdout)["tracks"]] == ["backend", "devops"]
