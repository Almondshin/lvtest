from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from lvtest.errors import LvtestError

AXIS_KEYS: list[str] = [
    "api_design",
    "data_db",
    "concurrency_perf",
    "architecture",
    "testing_quality",
    "ops_infra",
    "security",
]


class Stage(BaseModel):
    goal: str
    pass_level: int = Field(ge=1, le=5)


class Axis(BaseModel):
    key: str
    name: str
    description: str
    levels: dict[int, list[str]]
    probes: dict[int, str]

    @model_validator(mode="after")
    def _check(self) -> "Axis":
        if set(self.levels) != {1, 2, 3, 4, 5}:
            raise ValueError(f"{self.key}: levels must be exactly 1..5")
        empty = [l for l, v in self.levels.items() if not v]
        if empty:
            raise ValueError(f"{self.key}: level {empty} has no anchor")
        if set(self.probes) != {1, 2, 3, 4}:
            raise ValueError(f"{self.key}: probes must be exactly 1..4")
        return self


class Rubric(BaseModel):
    version: str
    track: str
    levels: dict[int, str]
    stages: dict[int, Stage]
    axes: list[Axis]

    @model_validator(mode="after")
    def _check(self) -> "Rubric":
        keys = [a.key for a in self.axes]
        if keys != AXIS_KEYS:
            raise ValueError(f"axes must be exactly {AXIS_KEYS} in order, got {keys}")
        if set(self.stages) != {1, 2, 3, 4}:
            raise ValueError("stages must be exactly 1..4")
        if set(self.levels) != {1, 2, 3, 4, 5}:
            raise ValueError("levels must be exactly 1..5")
        return self

    @property
    def axis_keys(self) -> list[str]:
        return [a.key for a in self.axes]

    def axis(self, key: str) -> Axis:
        for a in self.axes:
            if a.key == key:
                return a
        raise KeyError(key)


def rubric_path(track: str) -> Path:
    return Path(__file__).parent / "rubric" / f"{track}.yaml"


def parse_rubric(data: dict) -> Rubric:
    try:
        axes = [Axis(key=k, **v) for k, v in data["axes"].items()]
        return Rubric(
            version=str(data["version"]),
            track=data["track"],
            levels=data["levels"],
            stages=data["stages"],
            axes=axes,
        )
    except (ValidationError, ValueError, KeyError, TypeError) as e:
        raise LvtestError("invalid_rubric", f"rubric is invalid: {e}") from e


def load_rubric(track: str = "backend") -> Rubric:
    path = rubric_path(track)
    if not path.exists():
        raise LvtestError("unknown_track", f"no rubric for track '{track}'", track=track)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_rubric(data)
