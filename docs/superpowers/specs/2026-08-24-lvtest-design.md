# lvtest — 이력서 기반 백엔드 레벨테스트 설계

- 작성일: 2026-08-24
- 상태: 승인됨 (구현 계획 작성 전)
- 형태: Claude Code 플러그인 (`/lvtest` 스킬) + 로컬 Python CLI

## 1. 목표

사용자가 자신의 백엔드 개발 실력을 **객관적으로** 확인할 수 있는 레벨테스트.
이력서(pdf / docx / md)를 읽고, 거기 적힌 프로젝트·기술 주장을 근거로 면접관처럼
**꼬리 질문**을 이어가며, 역량 축별 확신이 충분해지면 자동 종료하고
**축별 1~5점 + 종합 L1~L5 레벨** 리포트를 낸다. 여러 번 응시하면 과거 결과와 비교한다.

UX는 ouroboros 인터뷰(`/ouroboros:interview`)에서 가져온다:

- 점수 기반 종료 (ouroboros의 "모호성 점수" → 여기서는 "축별 확신도")
- 가장 불확실한 축을 계속 파고드는 질문 선택
- 결정론적 엔진과 LLM의 역할 분리 (ouroboros의 MCP=질문생성기 / 메인세션=라우터)
- 세션 상태 영속화로 중단·재개 가능

가져오지 않는 것: MCP 서버 배관. 결정론 부분은 CLI로 둔다 (§2 결정 이유 참고).

## 2. 확정된 결정

| 결정 | 선택 | 기각한 대안과 이유 |
|---|---|---|
| 실행 형태 | Claude Code 플러그인/스킬 | 독립 CLI·웹앱: LLM 호출·API 키 관리가 늘고, Claude Code 안에서 쓰는 게 목적에 맞음 |
| 평가 근거 | 이력서 텍스트만 (v1) | 로컬 레포 지정 / 링크 자동 clone: v2로 미룸 |
| 결과 형태 | 축별 점수 + 종합 레벨 + 근거 인용 + 보완 포인트 | 종합 레벨만 / 서술 피드백만: 어디가 약한지 안 보임 |
| 종료 조건 | 확신도 기반 자동 종료 (상한 25문항) | 고정 문항 수: 확정된 축에 문항 낭비 |
| 답변 방식 | 채팅 자유 서술 | AskUserQuestion 선택지: 서술형이 실력 변별에 유리 |
| 이력 추적 | 과거 세션과 축별 비교 | 매번 독립: 실력 변화를 보려는 목적과 안 맞음 |
| 레벨 척도 | L1 입문 / L2 주니어 / L3 미드 / L4 시니어 / L5 스태프 | 연차 환산·100점 만점: 기준을 코드에 고정하기 어려움 |
| 구현 방식 | **B: 스킬 + 로컬 Python CLI** | A 순수 프롬프트: 채점·종료·상태를 모델이 매번 "알아서" 해서 응시마다 기준이 흔들리고 테스트 불가. C MCP 서버: deferred 툴 로딩 등 배관이 많고 얻는 게 없음. B로 만들면 나중에 MCP로 감싸기 쉬움 |

객관성의 근거는 세 가지다: (1) 루브릭이 YAML로 코드에 고정, (2) 점수·확신도·종료·다음
질문 선택이 전부 결정론적 CLI, (3) LLM 출력(채점)은 스키마 검증을 통과해야만 기록.

## 3. 전체 구조

### 3-1. 레포 구조 (이 레포가 곧 플러그인)

```
lvtest/
├── .claude-plugin/plugin.json      # 플러그인 메타
├── skills/lvtest/SKILL.md          # Claude용 진행 절차 + 면접관 규칙
├── src/lvtest/
│   ├── cli.py                      # `lvtest` 진입점. 모든 출력은 stdout JSON 한 덩어리
│   ├── resume.py                   # pdf / docx / md → 텍스트
│   ├── session.py                  # 세션 상태 저장/로드
│   ├── rubric.py                   # 루브릭 YAML 로드·스키마 검증
│   ├── scoring.py                  # 축 추정치·확신도·종합 레벨·종료 판정
│   ├── selector.py                 # 다음 축·깊이 단계 선택 (꼬리 질문 결정)
│   ├── report.py                   # 마크다운 리포트 렌더 + 과거 비교
│   └── rubric/backend.yaml         # 7축 × L1~L5 앵커 + 단계별 탐침 가이드
├── tests/
├── docs/superpowers/specs/
└── pyproject.toml
```

- Python 3.11+, `uv`로 실행. 의존성: `pypdf`, `python-docx`, `pydantic`, `pyyaml`, `typer`. 테스트: `pytest`.
- 저장 위치: `~/.lvtest/` (환경변수 `LVTEST_HOME`으로 변경 가능)
  - `sessions/<id>.json` — 세션 상태
  - `reports/YYYY-MM-DD-<id>.md` — 리포트
  - `reports/index.json` — 이력 인덱스
- `SKILL.md`는 `uv run --directory ${CLAUDE_PLUGIN_ROOT} lvtest …`로 CLI를 호출한다.
  설치 없이 `claude --plugin-dir ~/dev/lvtest`로 쓴다.

### 3-2. 역할 분담

| 담당 | 하는 일 |
|---|---|
| **CLI (결정론)** | 이력서 추출, 상태 저장, 다음 축/깊이 선택, 채점 JSON 검증, 점수·확신도 계산, 종료 판정, 리포트 렌더링, 과거 비교 |
| **Claude (LLM)** | 이력서 프로파일링(축별 근거 추출), 질문 문장 작성, 답변을 루브릭 앵커에 대조한 채점 JSON, 종료 후 총평 한 단락 |
| **사용자** | 채팅으로 답변 |

### 3-3. 한 턴의 흐름

```
Claude: lvtest next <id>  ──► {axis, stage, anchors, thread, hooks, avoid}
Claude: 질문 하나 작성 → 채팅 출력 → lvtest ask <id> --question "…" → 턴 종료
사용자: 채팅으로 답변
Claude: 답변을 앵커에 대조 → 채점 JSON → lvtest grade <id> --json '…'
CLI:    {continue: true,  progress: {...}}  → 다시 next
        {continue: false, reason: done|max}  → lvtest finish
사용자가 "그만/종료" → Claude: lvtest finish <id> --reason user_stop
```

## 4. CLI 계약

모든 명령은 stdout에 JSON 객체 하나를 출력한다. 실패 시 exit code 1 +
`{"error": {"code": "...", "message": "..."}}`. 진단 로그는 stderr.

| 명령 | 입력 | 출력 |
|---|---|---|
| `lvtest start <resume-path> [--track backend]` | 이력서 경로 | `{session_id, track, rubric_version, resume_text, resume_chars, warnings[], axes[{key, name, description}], avoid_questions[]}` |
| `lvtest profile <id> --json '<profile>'` | 프로파일 JSON (§5-2) | `{ok, axes_covered, axes_without_hooks[]}` |
| `lvtest next <id>` | — | `{axis, axis_name, stage, stage_goal, pass_level, anchors{level: [..]}, probe_guide, thread[{question, answer, level_evidence}], hooks[], avoid[], progress}` 또는 `{continue: false, reason}` |
| `lvtest ask <id> --question "<text>"` | 질문 원문 | `{ok, question_no}` |
| `lvtest grade <id> --json '<grade>'` | 채점 JSON (§5-3) | `{ok, continue, reason?, thread_status: "continue"\|"closed", progress}` 또는 검증 오류 `{error: {code: "invalid_grade", fields: {...}}}` |
| `lvtest status <id>` | — | `{state, next_action, last_question?, progress, session_summary}` |
| `lvtest finish <id> [--reason done\|max\|user_stop] [--summary "<text>"]` | 총평(선택) | `{report_path, overall, axes{key: {score, confidence}}, comparison?}` |
| `lvtest history` | — | `{sessions: [{id, date, overall, rubric_version, report_path}]}` |
| `lvtest sessions` | — | 미종료 세션 목록 (status 복구용) |

`progress`는 항상 `{question_no, max_questions, axes_confirmed, axes_total}`.

`status.state` ∈ `need_profile | need_question | awaiting_answer | need_finish | finished`.
`next_action`은 그 상태에서 Claude가 해야 할 일을 한 문장으로 준다 (컨텍스트 압축 후 복구용).
`session_summary`는 `{question_no, axes: {key: {score, confidence, threads}}}`.

**상태 머신 강제.** 각 명령은 허용된 상태에서만 동작한다. 아니면
`{"error": {"code": "invalid_state", "state": "...", "expected": ["..."]}}`.

| 명령 | 허용 상태 | 전이 |
|---|---|---|
| `profile` | `need_profile` | → `need_question` |
| `next` | `need_question` | 상태 유지 (질문 후보만 반환) / 후보 없으면 `continue:false` |
| `ask` | `need_question` | → `awaiting_answer` |
| `grade` | `awaiting_answer` | → `need_question` 또는 (종료 조건) `need_finish` |
| `finish` | `need_question`, `awaiting_answer`, `need_finish`, `finished` | → `finished` |

`finish`는 멱등이다. 이미 `finished`면 같은 리포트를 다시 렌더링한다.
`--reason` 생략 시 `grade`가 마지막으로 기록한 종료 사유(`done`/`max`)를 쓰고, 없으면 `user_stop`.
총평은 두 단계로 쓴다: `finish <id>`로 수치를 받고 → Claude가 총평을 쓴 뒤 `finish <id> --summary "…"`로
다시 호출하면 리포트가 총평을 포함해 갱신된다.

## 5. 데이터 스키마

### 5-1. 세션 (`sessions/<id>.json`)

```json
{
  "id": "20260824-a1b2c3",
  "created_at": "2026-08-24T11:30:00+09:00",
  "track": "backend",
  "rubric_version": "1",
  "resume": {"path": "...", "sha256": "...", "text": "...", "chars": 5120},
  "profile": { "<axis>": {"relevance": 0.9, "hooks": ["..."]} },
  "threads": [
    {"axis": "data_db", "hook": "...", "stage": 2, "open": true,
     "turns": [{"question_no": 3, "question": "...", "answer_grade": {...}}]}
  ],
  "questions": [{"no": 1, "axis": "...", "thread_idx": 0, "stage": 1, "text": "...", "asked_at": "..."}],
  "state": "awaiting_answer",
  "end_reason": null,
  "finished": null,
  "avoid_questions": ["과거 세션 질문 원문 ..."]
}
```

축별 추정치·확신도는 저장하지 않고 매번 `threads`에서 재계산한다 (단일 진실 원천).

### 5-2. 프로파일 JSON (Claude → `profile`)

```json
{
  "data_db":  {"relevance": 0.9, "hooks": ["주문 서비스 재고 차감 시 비관적 락 적용", "MySQL→PostgreSQL 마이그레이션 주도"]},
  "security": {"relevance": 0.2, "hooks": []}
}
```

- 7축 모두 필수. `relevance` ∈ [0, 1]. `hooks`는 이력서에 **적힌 주장**을 그대로 옮긴 문장 (최대 5개).
- hooks가 비어 있는 축은 `axes_without_hooks`로 돌려주며, 그 축의 질문은 사용자의 프로젝트 중 하나를
  골라 "그 프로젝트에서 X는 어떻게 처리했나요?" 형태로 붙인다 (일반 지식 문제로 만들지 않는다).

### 5-3. 채점 JSON (Claude → `grade`)

```json
{
  "axis": "data_db",
  "level_evidence": 3,
  "strength": 0.8,
  "answer_kind": "answered",
  "signals": ["격리 수준 선택 근거 설명", "데드락 사례 언급"],
  "gaps": ["팬텀 리드 언급 없음"],
  "quote": "저희는 REPEATABLE READ에서 …"
}
```

`strength` 기준 (SKILL.md에도 동일하게 명시):

- 0.2~0.4: 모호하거나 일반론, 전해 들은 이야기, 질문과 어긋난 답
- 0.5~0.7: 구체적이지만 부분적, 또는 기술적으로 일부 부정확
- 0.8~1.0: 구체적이고 직접 경험이며 기술적으로 정확, 수치·상황·결과가 있음

검증 규칙:

- `axis`는 `next`가 준 축과 일치해야 한다.
- `level_evidence` ∈ {1..5} 정수, `strength` ∈ [0, 1].
- `answer_kind` ∈ `answered | dont_know | pass`.
- `answered`면 `quote` 비어 있으면 안 됨 (리포트 근거).
- `dont_know` / `pass`면 CLI가 값을 **강제 덮어씀**: `level_evidence = pass_level − 1` (최소 1),
  `strength = 0.5`. 회피도 근거로 친다.
- 검증 실패 시 필드별 오류를 돌려주고 Claude가 최대 2회 재시도. 그래도 실패하면
  `strength = 0.3`, `level_evidence = pass_level − 1`, `answer_kind = "ungradable"`로 기록하고 진행한다.
  인터뷰가 멈추지 않는 것이 우선이다.

### 5-4. 루브릭 YAML (`rubric/backend.yaml`)

```yaml
version: "1"
track: backend
levels:            # 종합 레벨 이름
  1: 입문
  2: 주니어
  3: 미드
  4: 시니어
  5: 스태프
stages:            # 꼬리 질문 깊이 단계 (모든 축 공통)
  1: {goal: "경험 확인 — 구체적으로 뭘 어떻게 했나", pass_level: 2}
  2: {goal: "근거 — 왜 그 선택을 했나, 대안은",       pass_level: 3}
  3: {goal: "트레이드오프·한계 — 단점은, 언제 깨지나", pass_level: 4}
  4: {goal: "심화 — 트래픽 10배·요구 변경·장애 시엔",  pass_level: 5}
axes:
  data_db:
    name: 데이터 모델링·DB·트랜잭션
    description: 스키마, 인덱스, 격리 수준, 락, 마이그레이션
    levels:
      1: ["ORM으로 CRUD를 만든다", "트랜잭션 개념을 설명하지 못한다"]
      2: ["기본 인덱스를 쓴다", "트랜잭션을 '묶는 것' 정도로 이해"]
      3: ["격리 수준 차이를 알고 실제 선택 근거를 말한다", "N+1을 인지하고 해결한 경험"]
      4: ["락 경합·데드락을 진단하고 설계로 회피한 경험", "마이그레이션을 무중단으로 설계"]
      5: ["데이터 모델 변경이 조직 전체에 미치는 영향을 관리한 경험", "일관성 모델을 요구사항에서 도출"]
    probes:
      1: "이력서 훅을 인용하고, 본인이 직접 한 부분과 범위를 특정하게 하라"
      2: "왜 그 격리 수준/락/스키마를 골랐는지, 대안과 비교하게 하라"
      3: "그 선택이 깨지는 상황(핫로우, 롱 트랜잭션, 스키마 변경)을 묻라"
      4: "데이터 10배·다중 리전·강한 일관성 요구로 조건을 바꿔라"
```

7개 축: `api_design`, `data_db`, `concurrency_perf`, `architecture`, `testing_quality`,
`ops_infra`, `security`. 각 축은 `name`, `description`, `levels` 1~5 (각 1개 이상 앵커),
`probes` 1~4가 모두 있어야 로드된다 (`rubric.py`가 검증).

## 6. 인터뷰 메커니즘

### 6-1. 축과 최소 커버리지

모든 축은 최소 1회 질문한다. 이력서 관련도는 **우선순위와 프레이밍**에만 영향을 주고 축을 제외하지 않는다.

### 6-2. 스레드와 깊이 단계 (꼬리 질문)

- 한 축을 팔 때 훅 하나를 잡아 **스레드**를 열고 단계 1부터 시작한다.
- 답변의 `level_evidence ≥ stage.pass_level`이면 같은 스레드에서 **다음 단계**로 꼬리 질문.
- 미달이거나 `dont_know` / `pass`면 스레드를 **닫는다**.
- 단계 4를 통과하면 스레드를 닫는다 (더 팔 곳 없음).
- 닫힌 뒤에도 그 축 확신도가 임계 미만이면 **다른 훅으로 새 스레드**. 축당 최대 2 스레드.
  훅이 하나뿐이면 같은 훅의 다른 측면으로 연다 (`avoid`에 이전 질문 포함).
- 2 스레드를 다 썼는데도 확신도 미달이면 그 축은 "미확정"으로 두고 다른 축으로 넘어간다.

### 6-3. 다음 축 선택 (`selector.py`)

1. 열린 스레드가 있으면 **무조건 그 스레드를 잇는다** (흐름 유지, 축 이동 금지).
2. 없으면 아직 한 번도 묻지 않은 축 중 `relevance`가 높은 순.
3. 다 물어봤으면 `priority = (1 − confidence) × (0.5 + 0.5 × relevance)`가 최대인 축.
   `confidence ≥ 0.7`로 확정된 축과 스레드 상한(2)에 걸린 축은 제외. 동률이면 루브릭 정의 순서.
4. 후보가 없으면 `continue: false, reason: "done"`.

### 6-4. 점수·확신도 (`scoring.py`)

축마다 그 축의 모든 턴(모든 스레드)을 근거 집합 E로 본다.

- 추정치 `score = Σ(strength × level_evidence) / Σstrength`. E가 비면 미정.
- 분산 `var = Σ(strength × (level_evidence − score)²) / Σstrength`
- 확신도 `confidence = min(1, Σstrength / 2) × (1 − min(var, 1) / 2)`
  - 튼튼한 답(strength 0.8) 2~3개면 확정. 답이 오락가락하면 분산 페널티로 더 물어본다.
- 확정 임계 `CONFIDENCE_THRESHOLD = 0.7`
- 종합 `overall = mean(score)` (7축 동일 가중). 미정 축이 있으면 그 축은 제외하고 평균, 리포트에 표시.
- 레벨 = `floor(overall + 0.5)`를 1~5로 클램프 (Python `round`의 은행가 반올림을 쓰지 않는다).
  가장 가까운 경계값(x.5)과의 거리가 0.25 이하면 "L3 (L4 경계)" 형태로 이웃 레벨을 표기한다.
  예: 3.4 → L3 (L4 경계), 3.6 → L4 (L3 경계), 3.2 → L3.
- 병목 = score가 가장 낮은 축.

### 6-5. 종료

| 사유 | 조건 |
|---|---|
| `done` | 모든 축 confidence ≥ 0.7 **and** 모든 축 1회 이상 질문, 또는 selector가 후보 없음 |
| `max` | `question_no ≥ 25` |
| `user_stop` | 사용자가 그만두겠다고 함 (Claude가 `finish --reason user_stop`) |

`max` / `user_stop`이면 리포트에 미확정 축을 "확신 부족"으로 표시한다.
예상 분량: 7축 × 2~3문항 ≈ 15~22문항.

### 6-6. 면접관 규칙 (`SKILL.md`에 고정)

- 한 번에 질문 **하나**. 한국어. 항상 이력서 훅을 인용하며 시작 ("이력서에 …라고 쓰셨는데").
- 질문은 `next`가 준 `stage_goal`과 `probe_guide`를 따른다. `avoid`의 질문과 같은 각도는 피한다.
- 인터뷰 중 **피드백·힌트·정답·점수 노출 금지**. "좋은 답변이네요" 같은 평가 금지, "네, 다음 질문입니다" 수준의 중립 확인만.
- 답에 정답이 들어간 유도 질문 금지.
- 힌트/정답 요청 → "종료 후 설명드리겠다"고 하고 마지막 질문을 다시 제시.
- 무관한 잡담 → 짧게 응대 후 마지막 질문 재제시.
- 진행 표시는 질문 앞에 `[8/25 · 확정 3/7]` 한 줄만.
- 채점은 답변 직후, 사용자에게 보이지 않게 (채점 JSON을 채팅에 그대로 출력하지 않는다).
- 흐름이 확실치 않으면 `lvtest status`를 실행하고 `next_action`대로 한다.
- 시작 전 `uv --version` 확인. 없으면 설치 안내 후 중단.

## 7. 리포트와 이력

### 7-1. 리포트 (`reports/YYYY-MM-DD-<id>.md`)

CLI가 세션 상태에서 결정론적으로 렌더링한다. Claude가 쓰는 부분은 `--summary` 총평 한 단락뿐.

```
# 백엔드 레벨테스트 결과 — 2026-08-24
## 종합: L3 미드 (L4 경계)      평균 3.4 · 병목 security 2.1
종료 사유: done (19문항) · 루브릭 v1
## 축별 결과
| 축 | 점수 | 확신 | 근거 (답변 인용) | 부족했던 것 |
## 강점 (상위 2축) / 약점 (하위 2축)
## 다음 레벨로 가려면            ← 약점 축의 "현재 레벨+1" 앵커를 루브릭에서 인용
## 지난 결과와 비교              ← 직전 세션이 있을 때만
## 총평                         ← Claude 작성 (없으면 섹션 생략)
## 부록: 전체 문답               ← 질문·답변 인용·단계 표시
```

- "근거" 열은 그 축의 `answered` 턴 중 strength가 가장 높은 턴의 `quote` (없으면 "—"). "부족했던 것"은 `gaps` 합집합.
- 터미널에는 종합 레벨 + 축별 한 줄 표만 출력하고 전체는 파일 경로로 안내한다.

### 7-2. 이력

- `finish`가 `reports/index.json`에 `{id, date, track, rubric_version, overall, level, axes{key: score}, report_path}`를 추가.
- 직전 세션(같은 트랙, `finished` 있음)과 축별 델타를 리포트에 표기. 루브릭 버전이 다르면 델타 대신 "루브릭 변경으로 비교 불가".
- **재출제 회피**: `start`가 과거 세션들의 질문 원문을 모아 세션의 `avoid_questions`에 넣고, `next`가 해당 축의 것을 `avoid`로 돌려준다. 완전 차단이 아니라 회피 지시다.
- 이력서 변경 여부는 `sha256`으로 기록만 하고 비교는 그대로 한다.

## 8. 에러 처리

| 상황 | 처리 |
|---|---|
| PDF에 텍스트 없음(스캔본) / 암호화 / docx 파싱 실패 / 확장자 미지원 | `start` 실패, `error.code` = `resume_unreadable`, "md로 변환해서 다시" 안내 |
| 이력서 텍스트 8,000자 초과 | 자르지 않고 저장, `warnings`에 표시. Claude가 `profile` 단계에서 알아서 요약 |
| 채점 JSON 검증 실패 | §5-3 규칙 (재시도 2회 → `ungradable` 기록 후 진행) |
| 컨텍스트 압축으로 흐름 유실 | `lvtest status` → `state`, `next_action`, `last_question` 으로 복구 |
| 세션 파일 손상 | `status`가 `error.code = session_corrupt` + `lvtest sessions` 안내 |
| 같은 이력서로 미종료 세션이 있음 | `start`가 경고와 함께 새 세션을 만든다 (이어서 하려면 `status <id>`) |
| `uv` 없음 | SKILL.md 첫 단계에서 확인, 설치 안내 후 중단 |

## 9. 테스트

**단위 (pytest)**

- `resume.py`: md / pdf / docx 픽스처 → 텍스트. 텍스트 없는 PDF → `resume_unreadable`.
- `rubric.py`: 정상 YAML 로드, 축·레벨·probe 누락 시 실패.
- `scoring.py`: 추정치·분산·확신도 수식, 분산 페널티, 경계 표기, 미정 축 제외, 종료 3가지 사유.
- `selector.py`: 열린 스레드 우선 / 미질문 축 우선 / 우선순위 공식 / 축당 2스레드 상한 / 단계 통과·미달·`dont_know` 시 스레드 상태.
- `grade` 검증: 범위·축 불일치·인용 누락 거부, `dont_know`/`pass` 강제값, `ungradable` 폴백.
- `report.py`: 렌더 스냅샷, 델타 계산, 루브릭 버전 불일치, 총평 유무.
- `session.py`: 저장/로드 왕복, 손상 파일 처리, `LVTEST_HOME`.

**통합**

- CLI 프로세스로 `start → profile → (next → ask → grade) × N → finish`를 가짜 채점으로 완주, 리포트 스냅샷 비교.
- 같은 입력 → 같은 리포트 (결정론). 두 번째 세션에서 비교 섹션과 `avoid`가 나오는지.

**수동**

- 실제 이력서로 `claude --plugin-dir ~/dev/lvtest` 한 번 완주 — SKILL.md 문구·흐름 검증.

## 10. v1 범위 밖

GitHub 레포 분석, 로컬 레포 지정, 다른 트랙(프론트/데이터/인프라), 웹 리포트, MCP 래핑, 한국어 외 언어, 축 가중치 조정 UI.

---

## 11. v0.2 — devops 트랙 추가 (2026-08-26)

10절에서 v1 범위 밖으로 미뤄 뒀던 **인프라 트랙**을 열었다. 트랙 seam(`start --track`, `rubric/<track>.yaml`)은 v1 설계 그대로 쓰고, 이를 막고 있던 전역 축 목록 검증만 걷어냈다.

- `rubric.py`
  - `AXIS_KEYS` → `BACKEND_AXIS_KEYS`, `DEVOPS_AXIS_KEYS` 로 분리. `Rubric` 검증은 **축 정확히 7개 · 키 중복 없음**만 보고, 축의 이름과 순서는 각 트랙 YAML이 정한다.
  - `TRACK_ALIASES` (`be`/`server` → `backend`, `ops`/`infra`/`sre` → `devops`)와 `resolve_track()`. 잘못된 값은 `unknown_track` + `available`.
  - `Rubric.label` — 리포트 제목에 쓰는 한국어 트랙 이름.
  - `load_rubric()` 은 YAML의 `track` 필드가 파일 이름과 어긋나면 `invalid_rubric`.
- `rubric/devops.yaml` — 7축(IaC·프로비저닝 / CI/CD·릴리스 / 컨테이너·오케스트레이션 / 관측·장애 대응 / 신뢰성·확장·용량 / 네트워크·인프라 / 보안·시크릿·컴플라이언스). stages·levels 구조는 backend와 동일.
- `engine.start` 는 별칭을 정규 트랙 이름으로 바꿔 세션에 저장한다. `avoid_questions` 와 미완료 세션 경고도 트랙을 구분한다.
- `lvtest tracks` — 트랙·별칭·축 목록을 JSON으로.

세션 스키마, 채점·점수·종료 규칙, 리포트 형식은 그대로다. 트랙별 리포트 비교는 v1의 `previous_entry` 가 이미 `track` 으로 필터하고 있었으므로 손대지 않았다.

**여전히 범위 밖**: 한 세션에서 두 트랙 동시 평가, 프론트/데이터 트랙, GitHub 레포 분석, 웹 리포트.
