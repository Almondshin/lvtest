import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "lvtest-home"
    monkeypatch.setenv("LVTEST_HOME", str(home))
    return home
