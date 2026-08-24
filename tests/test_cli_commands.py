import json
import os
import subprocess
import sys

from typer.testing import CliRunner

from lvtest.cli import app
from tests.conftest import PROFILE

runner = CliRunner()


def _ok(args, input=None):
    r = runner.invoke(app, args, input=input)
    assert r.exit_code == 0, r.stdout
    return json.loads(r.stdout)


def _err(args, input=None):
    r = runner.invoke(app, args, input=input)
    assert r.exit_code == 1, r.stdout
    return json.loads(r.stdout)["error"]


def _resume(tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("# 김개발\n- 재고 차감에 비관적 락 적용\n", encoding="utf-8")
    return str(p)


def test_start_and_profile_via_stdin(tmp_path):
    out = _ok(["start", _resume(tmp_path)])
    sid = out["session_id"]
    assert out["resume_chars"] > 0 and len(out["axes"]) == 7
    prof = _ok(["profile", sid, "--json", "-"], input=json.dumps(PROFILE, ensure_ascii=False))
    assert prof["ok"] and prof["axes_without_hooks"] == ["security"]


def test_profile_inline_json(tmp_path):
    sid = _ok(["start", _resume(tmp_path)])["session_id"]
    assert _ok(["profile", sid, "--json", json.dumps(PROFILE, ensure_ascii=False)])["ok"]


def test_invalid_json_is_reported(tmp_path):
    sid = _ok(["start", _resume(tmp_path)])["session_id"]
    err = _err(["profile", sid, "--json", "{not json"])
    assert err["code"] == "invalid_json"


def test_domain_error_exit_code(tmp_path):
    err = _err(["start", str(tmp_path / "missing.md")])
    assert err["code"] == "resume_unreadable"
    assert _err(["status", "nope"])["code"] == "session_not_found"


def test_interview_commands(tmp_path):
    sid = _ok(["start", _resume(tmp_path)])["session_id"]
    _ok(["profile", sid, "--json", json.dumps(PROFILE, ensure_ascii=False)])
    nxt = _ok(["next", sid])
    assert nxt["continue"] and nxt["axis"] == "data_db"
    assert _ok(["ask", sid, "--question", "첫 질문"])["question_no"] == 1
    st = _ok(["status", sid])
    assert st["state"] == "awaiting_answer" and st["last_question"] == "첫 질문"
    grade = {"axis": "data_db", "level_evidence": 3, "strength": 0.8, "quote": "인용"}
    g = _ok(["grade", sid, "--json", "-"], input=json.dumps(grade, ensure_ascii=False))
    assert g["continue"] and g["thread_status"] == "continue"
    _ok(["ask", sid, "--question", "둘째 질문"])
    g2 = _ok(["grade", sid, "--ungradable"])
    assert g2["thread_status"] == "closed"
    err = _err(["grade", sid, "--json", "{}"])
    assert err["code"] == "invalid_state"
    fin = _ok(["finish", sid, "--reason", "user_stop", "--summary", "중간 총평"])
    assert fin["end_reason"] == "user_stop" and fin["has_summary"]
    assert _ok(["history"])["sessions"][0]["id"] == sid
    assert _ok(["sessions"])["sessions"] == []


def test_grade_requires_json_or_ungradable(tmp_path):
    sid = _ok(["start", _resume(tmp_path)])["session_id"]
    err = _err(["grade", sid])
    assert err["code"] == "invalid_json"


def test_module_entrypoint(tmp_path, isolated_home):
    env = {**os.environ, "LVTEST_HOME": str(isolated_home)}
    r = subprocess.run([sys.executable, "-m", "lvtest.cli", "--version"], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "lvtest" in json.loads(r.stdout)
