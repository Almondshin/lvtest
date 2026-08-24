import os
from pathlib import Path


def lvtest_home() -> Path:
    return Path(os.environ.get("LVTEST_HOME", str(Path.home() / ".lvtest"))).expanduser()


def sessions_dir() -> Path:
    d = lvtest_home() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def reports_dir() -> Path:
    d = lvtest_home() / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d
