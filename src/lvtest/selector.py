from __future__ import annotations

from dataclasses import dataclass

from lvtest.models import Session
from lvtest.rubric import Rubric
from lvtest.scoring import CONFIDENCE_THRESHOLD, MAX_THREADS_PER_AXIS, AxisStats


@dataclass(frozen=True)
class Choice:
    axis: str
    thread_idx: int | None  # None => open a new thread
    stage: int
    hook: str


def _relevance(session: Session, axis: str) -> float:
    if session.profile and axis in session.profile:
        return session.profile[axis].relevance
    return 0.0


def pick_hook(session: Session, axis: str) -> str:
    hooks = session.profile[axis].hooks if session.profile and axis in session.profile else []
    used = {t.hook for t in session.threads if t.axis == axis}
    for h in hooks:
        if h not in used:
            return h
    return hooks[0] if hooks else ""


def choose_next(session: Session, rubric: Rubric, stats: dict[str, AxisStats]) -> Choice | None:
    idx = session.open_thread_index()
    if idx is not None:
        t = session.threads[idx]
        return Choice(axis=t.axis, thread_idx=idx, stage=t.stage, hook=t.hook)

    keys = rubric.axis_keys

    def order(k: str) -> int:
        return -keys.index(k)  # earlier in rubric wins ties

    unasked = [k for k in keys if not stats[k].asked and stats[k].thread_count < MAX_THREADS_PER_AXIS]
    if unasked:
        axis = max(unasked, key=lambda k: (_relevance(session, k), order(k)))
    else:
        candidates = [
            k for k in keys
            if stats[k].confidence < CONFIDENCE_THRESHOLD and stats[k].thread_count < MAX_THREADS_PER_AXIS
        ]
        if not candidates:
            return None
        axis = max(
            candidates,
            key=lambda k: ((1.0 - stats[k].confidence) * (0.5 + 0.5 * _relevance(session, k)), order(k)),
        )
    return Choice(axis=axis, thread_idx=None, stage=1, hook=pick_hook(session, axis))
