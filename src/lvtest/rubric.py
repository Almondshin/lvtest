from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from lvtest.errors import LvtestError

BACKEND_AXIS_KEYS: list[str] = [
    "api_design",
    "data_db",
    "concurrency_perf",
    "architecture",
    "testing_quality",
    "ops_infra",
    "security",
]

DEVOPS_AXIS_KEYS: list[str] = [
    "iac_provisioning",
    "cicd_delivery",
    "container_orchestration",
    "observability_incident",
    "reliability_scaling",
    "network_infra",
    "security_compliance",
]

# 트랙이 달라도 축 개수는 7로 고정한다 — 25문항 안에서 축당 확신도를 채울 수 있는 상한이다.
AXIS_COUNT = 7

DEFAULT_TRACK = "backend"

# 사용자가 /lvtest 에 쓰는 별칭 -> 루브릭 파일 이름
TRACK_ALIASES: dict[str, str] = {
    "backend": "backend",
    "be": "backend",
    "server": "backend",
    "devops": "devops",
    "ops": "devops",
    "infra": "devops",
    "sre": "devops",
}


def available_tracks() -> list[str]:
    return sorted(set(TRACK_ALIASES.values()))


def resolve_track(track: str | None) -> str:
    """별칭('be', 'infra', ...)을 루브릭 트랙 이름으로 바꾼다. 빈 값은 기본 트랙."""
    key = (track or "").strip().lower()
    if not key:
        return DEFAULT_TRACK
    if key not in TRACK_ALIASES:
        raise LvtestError(
            "unknown_track",
            f"unknown track '{track}'; use one of {available_tracks()} "
            f"(aliases: {sorted(TRACK_ALIASES)})",
            track=track,
            available=available_tracks(),
        )
    return TRACK_ALIASES[key]


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
    label: str
    levels: dict[int, str]
    stages: dict[int, Stage]
    axes: list[Axis]

    @model_validator(mode="after")
    def _check(self) -> "Rubric":
        keys = [a.key for a in self.axes]
        if len(keys) != AXIS_COUNT:
            raise ValueError(f"a track must have exactly {AXIS_COUNT} axes, got {len(keys)}: {keys}")
        if len(set(keys)) != len(keys):
            raise ValueError(f"axis keys must be unique, got {keys}")
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
            label=data.get("label") or data["track"],
            levels=data["levels"],
            stages=data["stages"],
            axes=axes,
        )
    except (ValidationError, ValueError, KeyError, TypeError) as e:
        raise LvtestError("invalid_rubric", f"rubric is invalid: {e}") from e


def load_rubric(track: str = DEFAULT_TRACK) -> Rubric:
    track = resolve_track(track)
    path = rubric_path(track)
    if not path.exists():
        raise LvtestError(
            "unknown_track",
            f"no rubric file for track '{track}'",
            track=track,
            available=available_tracks(),
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rubric = parse_rubric(data)
    if rubric.track != track:
        raise LvtestError(
            "invalid_rubric",
            f"rubric file {path.name} declares track '{rubric.track}' but was loaded as '{track}'",
            track=track,
        )
    return rubric
