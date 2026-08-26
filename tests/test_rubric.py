import pytest

from lvtest.errors import LvtestError
from lvtest.rubric import BACKEND_AXIS_KEYS, load_rubric, parse_rubric


def test_backend_rubric_loads_with_seven_axes():
    r = load_rubric("backend")
    assert r.version == "1"
    assert r.track == "backend"
    assert r.axis_keys == BACKEND_AXIS_KEYS == [
        "api_design", "data_db", "concurrency_perf", "architecture",
        "testing_quality", "ops_infra", "security",
    ]
    assert r.levels[3] == "미드"
    assert {s: r.stages[s].pass_level for s in (1, 2, 3, 4)} == {1: 2, 2: 3, 3: 4, 4: 5}
    for axis in r.axes:
        assert set(axis.levels) == {1, 2, 3, 4, 5}
        assert all(axis.levels[l] for l in axis.levels)
        assert set(axis.probes) == {1, 2, 3, 4}


def test_axis_lookup():
    r = load_rubric()
    assert r.axis("data_db").name.startswith("데이터")
    with pytest.raises(KeyError):
        r.axis("nope")


def test_unknown_track_raises():
    with pytest.raises(LvtestError) as ei:
        load_rubric("frontend")
    assert ei.value.code == "unknown_track"


def _minimal_axis():
    return {
        "name": "n", "description": "d",
        "levels": {1: ["a"], 2: ["a"], 3: ["a"], 4: ["a"], 5: ["a"]},
        "probes": {1: "p", 2: "p", 3: "p", 4: "p"},
    }


def _minimal_data():
    return {
        "version": "1", "track": "backend", "label": "백엔드",
        "levels": {1: "a", 2: "b", 3: "c", 4: "d", 5: "e"},
        "stages": {1: {"goal": "g", "pass_level": 2}, 2: {"goal": "g", "pass_level": 3},
                   3: {"goal": "g", "pass_level": 4}, 4: {"goal": "g", "pass_level": 5}},
        "axes": {k: _minimal_axis() for k in BACKEND_AXIS_KEYS},
    }


def test_parse_rejects_missing_level_anchor():
    data = _minimal_data()
    data["axes"]["security"]["levels"][4] = []
    with pytest.raises(LvtestError) as ei:
        parse_rubric(data)
    assert ei.value.code == "invalid_rubric"
    assert "security" in ei.value.message


def test_parse_rejects_wrong_axis_count():
    data = _minimal_data()
    del data["axes"]["security"]
    with pytest.raises(LvtestError) as ei:
        parse_rubric(data)
    assert ei.value.code == "invalid_rubric"
    assert "7" in ei.value.message


def test_parse_keeps_the_axis_order_the_file_declares():
    data = _minimal_data()
    axes = data["axes"]
    data["axes"] = {k: axes[k] for k in reversed(BACKEND_AXIS_KEYS)}
    assert parse_rubric(data).axis_keys == list(reversed(BACKEND_AXIS_KEYS))


def test_load_rejects_rubric_whose_track_field_disagrees_with_its_filename(tmp_path, monkeypatch):
    import yaml

    from lvtest import rubric as rubric_mod

    data = _minimal_data()
    data["track"] = "devops"
    path = tmp_path / "backend.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(rubric_mod, "rubric_path", lambda track: tmp_path / f"{track}.yaml")
    with pytest.raises(LvtestError) as ei:
        load_rubric("backend")
    assert ei.value.code == "invalid_rubric"
