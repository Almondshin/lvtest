from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from lvtest.errors import LvtestError
from lvtest.models import AvoidQuestion, ProfileAxis, ResumeInfo, Session
from lvtest.resume import extract_text
from lvtest.rubric import Rubric, load_rubric
from lvtest.session import list_sessions, load_session, new_session_id, save_session
from lvtest.grading import ungradable_grade, validate_grade
from lvtest.models import Grade, Thread, Turn
from lvtest.scoring import MAX_QUESTIONS, AxisStats, compute_all, termination_reason
from lvtest.selector import choose_next

RESUME_WARN_CHARS = 8000


def _now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now().astimezone()


def _stamp(now: datetime | None) -> str:
    return _now(now).isoformat(timespec="seconds")


def _require_state(session: Session, *allowed: str) -> None:
    if session.state not in allowed:
        raise LvtestError(
            "invalid_state",
            f"command not allowed in state '{session.state}'",
            state=session.state,
            expected=list(allowed),
        )


def _axes_payload(rubric: Rubric) -> list[dict]:
    return [{"key": a.key, "name": a.name, "description": a.description} for a in rubric.axes]


def start(
    resume_path: str,
    track: str = "backend",
    now: datetime | None = None,
    session_id: str | None = None,
) -> dict:
    rubric = load_rubric(track)
    path = Path(resume_path).expanduser()
    text = extract_text(path)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

    warnings: list[str] = []
    if len(text) > RESUME_WARN_CHARS:
        warnings.append(f"resume text is {len(text)} chars (> {RESUME_WARN_CHARS}); summarize key claims during profiling")

    past = list_sessions()
    for s in past:
        if s.finished is None and s.resume.sha256 == sha and s.id != session_id:
            warnings.append(f"unfinished session '{s.id}' exists for this resume; `lvtest status {s.id}` to continue it")
    avoid = [q for s in past if s.finished for q in s.all_questions()]

    ts = _now(now)
    session = Session(
        id=session_id or new_session_id(ts),
        created_at=ts.isoformat(timespec="seconds"),
        track=track,
        rubric_version=rubric.version,
        resume=ResumeInfo(path=str(path), sha256=sha, text=text, chars=len(text)),
        avoid_questions=avoid,
    )
    save_session(session)
    return {
        "session_id": session.id,
        "track": track,
        "rubric_version": rubric.version,
        "resume_text": text,
        "resume_chars": len(text),
        "warnings": warnings,
        "axes": _axes_payload(rubric),
        "avoid_questions": [a.model_dump() for a in avoid],
    }


def profile(session_id: str, data: dict) -> dict:
    session = load_session(session_id)
    _require_state(session, "need_profile")
    rubric = load_rubric(session.track)
    if not isinstance(data, dict):
        raise LvtestError("invalid_profile", "profile must be a JSON object", fields={"_": "not an object"})
    fields: dict[str, str] = {k: "missing" for k in rubric.axis_keys if k not in data}
    parsed: dict[str, ProfileAxis] = {}
    for k in rubric.axis_keys:
        if k in fields:
            continue
        try:
            parsed[k] = ProfileAxis.model_validate(data[k])
        except ValidationError as e:
            fields[k] = "; ".join(err["msg"] for err in e.errors())
    if fields:
        raise LvtestError("invalid_profile", "profile validation failed; fix the listed axes and retry", fields=fields)
    session.profile = parsed
    session.state = "need_question"
    save_session(session)
    return {
        "ok": True,
        "axes_covered": [k for k in rubric.axis_keys if parsed[k].hooks],
        "axes_without_hooks": [k for k in rubric.axis_keys if not parsed[k].hooks],
    }


def _progress(session: Session, stats: dict[str, AxisStats]) -> dict:
    return {
        "question_no": session.question_no,
        "max_questions": MAX_QUESTIONS,
        "axes_confirmed": sum(1 for s in stats.values() if s.confirmed),
        "axes_total": len(stats),
    }


def _ended(session: Session, stats: dict[str, AxisStats], rubric: Rubric) -> str | None:
    reason = termination_reason(session, stats)
    if reason is None and choose_next(session, rubric, stats) is None:
        reason = "done"
    return reason


def next_question(session_id: str) -> dict:
    session = load_session(session_id)
    _require_state(session, "need_question", "need_finish")
    rubric = load_rubric(session.track)
    stats = compute_all(session, rubric)
    reason = session.end_reason if session.state == "need_finish" else _ended(session, stats, rubric)
    if reason:
        return {"continue": False, "reason": reason, "progress": _progress(session, stats)}
    choice = choose_next(session, rubric, stats)
    assert choice is not None  # _ended() guarantees a candidate exists
    axis = rubric.axis(choice.axis)
    stage = rubric.stages[choice.stage]
    thread_turns = session.threads[choice.thread_idx].turns if choice.thread_idx is not None else []
    hooks = session.profile[axis.key].hooks if session.profile and axis.key in session.profile else []
    return {
        "continue": True,
        "axis": axis.key,
        "axis_name": axis.name,
        "stage": choice.stage,
        "stage_goal": stage.goal,
        "pass_level": stage.pass_level,
        "anchors": {str(level): anchors for level, anchors in sorted(axis.levels.items())},
        "probe_guide": axis.probes[choice.stage],
        "hook": choice.hook,
        "hooks": hooks,
        "thread": [
            {
                "question": t.question,
                "stage": t.stage,
                "level_evidence": t.grade.level_evidence if t.grade else None,
                "quote": t.grade.quote if t.grade else None,
            }
            for t in thread_turns
        ],
        "avoid": [a.text for a in session.avoid_questions if a.axis == axis.key],
        "progress": _progress(session, stats),
    }


def ask(session_id: str, question: str, now: datetime | None = None) -> dict:
    session = load_session(session_id)
    _require_state(session, "need_question")
    if not question or not question.strip():
        raise LvtestError("invalid_question", "question text is empty")
    rubric = load_rubric(session.track)
    stats = compute_all(session, rubric)
    if _ended(session, stats, rubric):
        raise LvtestError("no_question", "interview should finish; run `lvtest finish`")
    choice = choose_next(session, rubric, stats)
    assert choice is not None
    if choice.thread_idx is None:
        session.threads.append(Thread(axis=choice.axis, hook=choice.hook))
        idx = len(session.threads) - 1
    else:
        idx = choice.thread_idx
    thread = session.threads[idx]
    turn = Turn(question_no=session.question_no + 1, stage=thread.stage, question=question.strip(), asked_at=_stamp(now))
    thread.turns.append(turn)
    session.state = "awaiting_answer"
    save_session(session)
    return {"ok": True, "question_no": turn.question_no, "axis": thread.axis, "stage": thread.stage}


def _pending(session: Session) -> tuple[Thread, Turn]:
    idx = session.open_thread_index()
    if idx is None or not session.threads[idx].turns or session.threads[idx].turns[-1].grade is not None:
        raise LvtestError("invalid_state", "no pending question to grade", state=session.state, expected=["awaiting_answer"])
    thread = session.threads[idx]
    return thread, thread.turns[-1]


def _record_grade(session: Session, rubric: Rubric, thread: Thread, turn: Turn, g: Grade) -> dict:
    turn.grade = g
    pass_level = rubric.stages[turn.stage].pass_level
    passed = g.answer_kind == "answered" and g.level_evidence >= pass_level
    if passed and thread.stage < 4:
        thread.stage += 1
        thread_status = "continue"
    else:
        thread.open = False
        thread_status = "closed"
    stats = compute_all(session, rubric)
    reason = _ended(session, stats, rubric)
    if reason:
        session.state = "need_finish"
        session.end_reason = reason
    else:
        session.state = "need_question"
    save_session(session)
    return {
        "ok": True,
        "continue": reason is None,
        "reason": reason,
        "thread_status": thread_status,
        "progress": _progress(session, stats),
    }


def grade(session_id: str, raw: dict) -> dict:
    session = load_session(session_id)
    _require_state(session, "awaiting_answer")
    rubric = load_rubric(session.track)
    thread, turn = _pending(session)
    g = validate_grade(raw, thread.axis, rubric.stages[turn.stage].pass_level)
    return _record_grade(session, rubric, thread, turn, g)


def grade_ungradable(session_id: str) -> dict:
    session = load_session(session_id)
    _require_state(session, "awaiting_answer")
    rubric = load_rubric(session.track)
    thread, turn = _pending(session)
    g = ungradable_grade(thread.axis, rubric.stages[turn.stage].pass_level)
    return _record_grade(session, rubric, thread, turn, g)


_NEXT_ACTION = {
    "need_profile": "resume_text를 읽고 7축 프로파일 JSON을 만들어 `lvtest profile <id> --json -` 로 저장하라",
    "need_question": "`lvtest next <id>` 를 실행하고 질문 하나를 작성해 채팅에 출력한 뒤 `lvtest ask <id> --question ...` 로 기록하라",
    "awaiting_answer": "사용자가 last_question 에 답하길 기다렸다가 채점 JSON을 만들어 `lvtest grade <id> --json -` 로 기록하라",
    "need_finish": "`lvtest finish <id>` 를 실행해 리포트를 만들고, 총평을 써서 `lvtest finish <id> --summary ...` 로 다시 호출하라",
    "finished": "인터뷰가 끝났다. report_path 의 리포트를 요약해 보여 주라",
}


def status(session_id: str) -> dict:
    session = load_session(session_id)
    rubric = load_rubric(session.track)
    stats = compute_all(session, rubric)
    last = session.last_turn()
    last_axis = None
    if last is not None:
        last_axis = next(t.axis for t in session.threads if last in t.turns)
    out = {
        "state": session.state,
        "next_action": _NEXT_ACTION[session.state],
        "last_question": last.question if last else None,
        "last_question_axis": last_axis,
        "end_reason": session.end_reason,
        "progress": _progress(session, stats),
        "session_summary": {
            "question_no": session.question_no,
            "axes": {
                k: {
                    "score": None if s.score is None else round(s.score, 2),
                    "confidence": round(s.confidence, 2),
                    "threads": s.thread_count,
                }
                for k, s in stats.items()
            },
        },
    }
    if session.finished:
        from lvtest.report import report_path_for  # 순환 import 회피

        out["report_path"] = str(report_path_for(session))
    return out
