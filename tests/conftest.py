from datetime import datetime, timezone

import pytest

from lvtest.models import ProfileAxis, ResumeInfo, Session


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

DEVOPS_PROFILE = {
    "iac_provisioning": {"relevance": 0.9, "hooks": ["Terraform으로 EKS 클러스터 프로비저닝"]},
    "cicd_delivery": {"relevance": 0.8, "hooks": ["ArgoCD로 GitOps 배포 파이프라인 구축"]},
    "container_orchestration": {"relevance": 0.7, "hooks": ["Kubernetes HPA로 오토스케일링 구성"]},
    "observability_incident": {"relevance": 0.6, "hooks": ["Prometheus·Grafana 대시보드 구축"]},
    "reliability_scaling": {"relevance": 0.5, "hooks": ["멀티 AZ 구성으로 가용성 확보"]},
    "network_infra": {"relevance": 0.4, "hooks": ["VPC 서브넷·보안 그룹 설계"]},
    "security_compliance": {"relevance": 0.1, "hooks": []},
}

PROFILES = {"backend": PROFILE, "devops": DEVOPS_PROFILE}


def make_session(**overrides) -> Session:
    track = overrides.pop("track", "backend")
    base = dict(
        id="20260824-120000-abc123",
        created_at=NOW.isoformat(timespec="seconds"),
        track=track,
        rubric_version="1",
        resume=ResumeInfo(path="/tmp/r.md", sha256="0" * 64, text="이력서 본문", chars=6),
        profile={k: ProfileAxis(**v) for k, v in PROFILES.get(track, PROFILE).items()},
        state="need_question",
    )
    base.update(overrides)
    return Session(**base)
