from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from lvtest.errors import LvtestError
from lvtest.models import Session
from lvtest.paths import sessions_dir


def new_session_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def session_path(session_id: str) -> Path:
    return sessions_dir() / f"{session_id}.json"


def save_session(session: Session) -> Path:
    path = session_path(session.id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _parse(path: Path) -> Session:
    try:
        return Session.model_validate_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise LvtestError(
            "session_corrupt",
            f"session file {path.name} is corrupt: {e}. Run `lvtest sessions` to see other sessions.",
            path=str(path),
        ) from e


def load_session(session_id: str) -> Session:
    path = session_path(session_id)
    if not path.exists():
        raise LvtestError("session_not_found", f"no session '{session_id}'. Run `lvtest sessions`.", session_id=session_id)
    return _parse(path)


def list_sessions() -> list[Session]:
    out: list[Session] = []
    for path in sessions_dir().glob("*.json"):
        try:
            out.append(_parse(path))
        except LvtestError:
            continue
    return sorted(out, key=lambda s: s.created_at)
