import json
from typer.testing import CliRunner

from lvtest import __version__
from lvtest.cli import app
from lvtest.paths import lvtest_home, sessions_dir


def test_version_prints_json():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"lvtest": __version__}


def test_home_respects_env(isolated_home):
    assert lvtest_home() == isolated_home
    assert sessions_dir() == isolated_home / "sessions"
    assert (isolated_home / "sessions").is_dir()
