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
