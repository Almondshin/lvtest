from __future__ import annotations

from lvtest.errors import LvtestError
from lvtest.models import Grade

_KINDS = ("answered", "dont_know", "pass")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _str_list(v) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else []


def validate_grade(raw: dict, expected_axis: str, pass_level: int) -> Grade:
    if not isinstance(raw, dict):
        raise LvtestError("invalid_grade", "grade must be a JSON object", fields={"_": "not an object"})
    fields: dict[str, str] = {}
    kind = raw.get("answer_kind", "answered")
    if kind not in _KINDS:
        fields["answer_kind"] = "must be one of answered|dont_know|pass"
    if raw.get("axis") != expected_axis:
        fields["axis"] = f"expected '{expected_axis}'"

    if kind in ("dont_know", "pass"):
        level = max(1, pass_level - 1)
        strength = 0.5
        quote = ""
    else:
        level = raw.get("level_evidence")
        if not _is_int(level) or not 1 <= level <= 5:
            fields["level_evidence"] = "integer 1..5"
        strength = raw.get("strength")
        if not _is_num(strength) or not 0 <= strength <= 1:
            fields["strength"] = "number 0..1"
        quote = str(raw.get("quote", ""))
        if not quote.strip():
            fields["quote"] = "required when answer_kind=answered (quote the answer)"

    if fields:
        raise LvtestError("invalid_grade", "grade validation failed; fix the listed fields and retry", fields=fields)
    return Grade(
        axis=expected_axis,
        level_evidence=int(level),
        strength=float(strength),
        answer_kind=kind,
        signals=_str_list(raw.get("signals")),
        gaps=_str_list(raw.get("gaps")),
        quote=quote,
    )


def ungradable_grade(axis: str, pass_level: int) -> Grade:
    return Grade(axis=axis, level_evidence=max(1, pass_level - 1), strength=0.3, answer_kind="ungradable", quote="")
