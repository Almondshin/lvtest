import pytest

from lvtest.errors import LvtestError
from lvtest.grading import ungradable_grade, validate_grade


GOOD = {
    "axis": "data_db", "level_evidence": 3, "strength": 0.8, "answer_kind": "answered",
    "signals": ["격리 수준 근거"], "gaps": ["팬텀 리드 언급 없음"], "quote": "저희는 REPEATABLE READ에서",
}


def test_valid_answered():
    g = validate_grade(GOOD, "data_db", pass_level=3)
    assert g.axis == "data_db" and g.level_evidence == 3 and g.strength == 0.8
    assert g.answer_kind == "answered" and g.signals == ["격리 수준 근거"] and g.quote.startswith("저희는")


def test_defaults_for_optional_lists():
    g = validate_grade({"axis": "data_db", "level_evidence": 2, "strength": 0.5, "quote": "x"}, "data_db", 2)
    assert g.signals == [] and g.gaps == [] and g.answer_kind == "answered"


@pytest.mark.parametrize("patch,field", [
    ({"axis": "security"}, "axis"),
    ({"level_evidence": 0}, "level_evidence"),
    ({"level_evidence": 6}, "level_evidence"),
    ({"level_evidence": 3.5}, "level_evidence"),
    ({"level_evidence": True}, "level_evidence"),
    ({"strength": 1.2}, "strength"),
    ({"strength": "high"}, "strength"),
    ({"quote": "  "}, "quote"),
    ({"answer_kind": "maybe"}, "answer_kind"),
])
def test_rejects_bad_fields(patch, field):
    with pytest.raises(LvtestError) as ei:
        validate_grade({**GOOD, **patch}, "data_db", 3)
    assert ei.value.code == "invalid_grade"
    assert field in ei.value.extra["fields"]


def test_reports_all_bad_fields_at_once():
    with pytest.raises(LvtestError) as ei:
        validate_grade({**GOOD, "level_evidence": 9, "strength": -1}, "data_db", 3)
    assert set(ei.value.extra["fields"]) == {"level_evidence", "strength"}


def test_not_an_object():
    with pytest.raises(LvtestError) as ei:
        validate_grade(["nope"], "data_db", 3)  # type: ignore[arg-type]
    assert ei.value.code == "invalid_grade"


@pytest.mark.parametrize("kind", ["dont_know", "pass"])
def test_dont_know_and_pass_force_values(kind):
    g = validate_grade({"axis": "data_db", "answer_kind": kind}, "data_db", pass_level=3)
    assert g.level_evidence == 2 and g.strength == 0.5 and g.answer_kind == kind and g.quote == ""


def test_forced_level_floor_is_one():
    g = validate_grade({"axis": "data_db", "answer_kind": "pass", "level_evidence": 5, "strength": 1.0}, "data_db", pass_level=2)
    assert g.level_evidence == 1 and g.strength == 0.5


def test_ungradable():
    g = ungradable_grade("security", pass_level=4)
    assert g.answer_kind == "ungradable" and g.level_evidence == 3 and g.strength == 0.3 and g.quote == ""
