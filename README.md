# lvtest — 이력서 기반 백엔드 레벨테스트

이력서(pdf / docx / md)를 읽고 면접관처럼 **꼬리 질문**을 이어가며 백엔드 역량 7개 축을 1~5점으로 채점하고 종합 레벨(L1 입문 ~ L5 스태프)을 판정하는 Claude Code 플러그인입니다.

- 결정론 엔진(루브릭·채점 검증·확신도·종료·리포트)은 Python CLI `lvtest`
- 질문 작성과 채점은 Claude Code 세션이 `skills/lvtest/SKILL.md` 절차대로 수행
- 결과는 `~/.lvtest/reports/` 에 마크다운으로 저장되고, 다음 응시 때 과거와 비교

## 요구 사항

- [uv](https://docs.astral.sh/uv/) (Python 3.11+ 는 uv가 관리)
- Claude Code

## 설치·실행

```bash
git clone https://github.com/Almondshin/lvtest ~/dev/lvtest
claude --plugin-dir ~/dev/lvtest
```

Claude Code 안에서:

```
/lvtest ~/Documents/resume.pdf
```

## 동작 방식

1. `lvtest start` 가 이력서 텍스트를 추출해 세션을 만든다.
2. Claude가 이력서에서 축별 근거(훅)를 뽑아 `lvtest profile` 로 저장한다.
3. 반복: `lvtest next` 가 **가장 불확실한 축**과 깊이 단계(S1 경험 → S2 근거 → S3 트레이드오프 → S4 심화)를 고르면 Claude가 질문을 쓰고, 답변을 루브릭에 대조해 채점 JSON을 `lvtest grade` 로 넘긴다. 답이 단계 기준을 넘으면 같은 주제로 더 파고들고, 막히면 다른 축으로 옮긴다.
4. 모든 축의 확신도가 0.7 이상이면(또는 25문항) 자동 종료 → `lvtest finish` 가 리포트를 만든다.

역량 축: API·서비스 설계 / 데이터 모델링·DB·트랜잭션 / 동시성·성능·캐싱 / 아키텍처·트레이드오프 / 테스트·품질 / 운영·배포·관측 / 보안·인증
루브릭: `src/lvtest/rubric/backend.yaml`

## 개발

```bash
uv sync
uv run pytest
uv run lvtest --help
```

설계 문서: `docs/superpowers/specs/2026-08-24-lvtest-design.md`
