from __future__ import annotations

import math
from dataclasses import dataclass

from lvtest.models import Session
from lvtest.rubric import Rubric

CONFIDENCE_THRESHOLD = 0.7
MAX_QUESTIONS = 25
MAX_THREADS_PER_AXIS = 2


@dataclass(frozen=True)
class AxisStats:
    score: float | None
    confidence: float
    variance: float
    evidence_count: int
    thread_count: int

    @property
    def asked(self) -> bool:
        return self.evidence_count > 0

    @property
    def confirmed(self) -> bool:
        return self.asked and self.confidence >= CONFIDENCE_THRESHOLD


def compute_axis_stats(session: Session, axis_key: str) -> AxisStats:
    grades = [t.grade for t in session.turns_for_axis(axis_key) if t.grade is not None]
    thread_count = sum(1 for t in session.threads if t.axis == axis_key)
    weight = sum(g.strength for g in grades)
    if not grades or weight <= 0:
        return AxisStats(None, 0.0, 0.0, len(grades), thread_count)
    score = sum(g.strength * g.level_evidence for g in grades) / weight
    variance = sum(g.strength * (g.level_evidence - score) ** 2 for g in grades) / weight
    confidence = min(1.0, weight / 2.0) * (1.0 - min(variance, 1.0) / 2.0)
    return AxisStats(score, confidence, variance, len(grades), thread_count)


def compute_all(session: Session, rubric: Rubric) -> dict[str, AxisStats]:
    return {k: compute_axis_stats(session, k) for k in rubric.axis_keys}


def level_from_overall(x: float) -> tuple[int, int | None]:
    level = max(1, min(5, math.floor(x + 0.5)))
    boundary = math.floor(x) + 0.5
    neighbor: int | None = None
    if abs(x - boundary) <= 0.25:
        neighbor = level + 1 if x < boundary else level - 1
        if not 1 <= neighbor <= 5 or neighbor == level:
            neighbor = None
    return level, neighbor


@dataclass(frozen=True)
class Overall:
    score: float | None
    level: int | None
    neighbor: int | None
    bottleneck: str | None
    undetermined: list[str]


def compute_overall(stats: dict[str, AxisStats]) -> Overall:
    scored = {k: v.score for k, v in stats.items() if v.score is not None}
    undetermined = [k for k, v in stats.items() if v.score is None]
    if not scored:
        return Overall(None, None, None, None, undetermined)
    avg = sum(scored.values()) / len(scored)
    level, neighbor = level_from_overall(avg)
    bottleneck = min(scored, key=lambda k: scored[k])
    return Overall(round(avg, 2), level, neighbor, bottleneck, undetermined)


def termination_reason(session: Session, stats: dict[str, AxisStats]) -> str | None:
    if session.question_no >= MAX_QUESTIONS:
        return "max"
    if all(s.confirmed for s in stats.values()):
        return "done"
    return None
