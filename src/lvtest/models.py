from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AnswerKind = Literal["answered", "dont_know", "pass", "ungradable"]
State = Literal["need_profile", "need_question", "awaiting_answer", "need_finish", "finished"]
EndReason = Literal["done", "max", "user_stop"]


class Grade(BaseModel):
    axis: str
    level_evidence: int = Field(ge=1, le=5)
    strength: float = Field(ge=0.0, le=1.0)
    answer_kind: AnswerKind = "answered"
    signals: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    quote: str = ""


class Turn(BaseModel):
    question_no: int
    stage: int
    question: str
    asked_at: str
    grade: Grade | None = None


class Thread(BaseModel):
    axis: str
    hook: str
    stage: int = 1
    open: bool = True
    turns: list[Turn] = Field(default_factory=list)


class ProfileAxis(BaseModel):
    relevance: float = Field(ge=0.0, le=1.0)
    hooks: list[str] = Field(default_factory=list, max_length=5)


class ResumeInfo(BaseModel):
    path: str
    sha256: str
    text: str
    chars: int


class AvoidQuestion(BaseModel):
    axis: str
    text: str


class Session(BaseModel):
    id: str
    created_at: str
    track: str
    rubric_version: str
    resume: ResumeInfo
    profile: dict[str, ProfileAxis] | None = None
    threads: list[Thread] = Field(default_factory=list)
    state: State = "need_profile"
    end_reason: EndReason | None = None
    finished: str | None = None
    summary: str | None = None
    avoid_questions: list[AvoidQuestion] = Field(default_factory=list)

    @property
    def question_no(self) -> int:
        return sum(len(t.turns) for t in self.threads)

    def open_thread_index(self) -> int | None:
        for i, t in enumerate(self.threads):
            if t.open:
                return i
        return None

    def turns_for_axis(self, axis: str) -> list[Turn]:
        return [turn for t in self.threads if t.axis == axis for turn in t.turns]

    def last_turn(self) -> Turn | None:
        turns = [turn for t in self.threads for turn in t.turns]
        return max(turns, key=lambda t: t.question_no) if turns else None

    def all_questions(self) -> list[AvoidQuestion]:
        turns = [(turn.question_no, t.axis, turn.question) for t in self.threads for turn in t.turns]
        return [AvoidQuestion(axis=a, text=q) for _, a, q in sorted(turns)]
