from datetime import datetime, timezone

import pytest

from lvtest.models import ProfileAxis, ResumeInfo, Session
from lvtest.rubric import AXIS_KEYS


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "lvtest-home"
    monkeypatch.setenv("LVTEST_HOME", str(home))
    return home


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

PROFILE = {
    "api_design": {"relevance": 0.6, "hooks": ["주문 API를 REST로 설계"]},
    "data_db": {"relevance": 0.9, "hooks": ["재고 차감에 비관적 락 적용", "PostgreSQL 마이그레이션 주도"]},
    "concurrency_perf": {"relevance": 0.7, "hooks": ["Redis 캐시로 응답 40% 개선"]},
    "architecture": {"relevance": 0.5, "hooks": ["모놀리스를 도메인별 모듈로 분리"]},
    "testing_quality": {"relevance": 0.3, "hooks": ["JUnit 통합 테스트 작성"]},
    "ops_infra": {"relevance": 0.4, "hooks": ["GitHub Actions로 배포 자동화"]},
    "security": {"relevance": 0.1, "hooks": []},
}


def make_session(**overrides) -> Session:
    base = dict(
        id="20260824-120000-abc123",
        created_at=NOW.isoformat(timespec="seconds"),
        track="backend",
        rubric_version="1",
        resume=ResumeInfo(path="/tmp/r.md", sha256="0" * 64, text="이력서 본문", chars=6),
        profile={k: ProfileAxis(**v) for k, v in PROFILE.items()},
        state="need_question",
    )
    base.update(overrides)
    return Session(**base)
