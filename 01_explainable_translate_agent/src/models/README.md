# 데이터 모델 (Data Models)

번역 워크플로우에서 사용하는 Pydantic 데이터 모델입니다.

## 파일 구조

```
src/models/
├── translation_unit.py      # 번역 입력 단위
├── agent_result.py          # 에이전트 평가 결과
├── gate_decision.py         # 게이트 판정 결과
└── workflow_state.py        # 워크플로우 상태
```

---

## TranslationUnit (번역 단위)

번역 요청의 입력 스키마. 단일 FAQ 항목과 번역에 필요한 컨텍스트를 포함합니다.

```python
from src.models import TranslationUnit

unit = TranslationUnit(
    key="IDS_FAQ_001",
    source_text="ABC 클라우드에서 동기화가 되지 않습니다.",
    target_lang="en-rUS",
    product="abc_cloud"  # glossary는 product로 자동 로드
)
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `key` | str | O | FAQ 키 |
| `source_text` | str | O | 원문 |
| `source_lang` | str | X | 소스 언어 (기본: "ko") |
| `target_lang` | str | O | 타겟 언어 |
| `product` | str | X | 제품 식별자 |
| `glossary` | Dict | X | 파일에서 자동 로드 (`product`/`target_lang`) |
| `style_guide` | Dict | X | 파일에서 자동 로드 (`product`/`target_lang`) |
| `risk_profile` | str | X | 파일에서 자동 로드 (기본: "DEFAULT") |

---

## AgentResult (에이전트 결과)

평가 에이전트의 출력. Chain-of-Thought로 설명가능성 제공.

```python
from src.models import AgentResult, Correction

result = AgentResult(
    agent_name="accuracy",
    score=4,
    verdict="pass",
    reasoning_chain=["의미 보존 확인", "용어집 검증 완료"],
    issues=[],
    corrections=[],
    latency_ms=1200
)
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `agent_name` | str | O | 에이전트 이름 (accuracy, compliance, quality) |
| `score` | int | O | 평가 점수 (0-5) |
| `verdict` | str | O | pass, fail, review |
| `reasoning_chain` | List[str] | X | CoT 분석 과정 |
| `issues` | List[str] | X | 발견된 문제점 |
| `corrections` | List[Correction] | X | 수정 제안 |
| `latency_ms` | int | X | 응답 시간 (ms) |

### Correction (수정 제안)

```python
Correction(
    original="ABC Cloud",
    suggested="ABC Cloud",
    reason="용어집 표기 준수"
)
```

---

## GateDecision (게이트 판정)

3개 에이전트 결과를 집계한 최종 판정.

```python
from src.models import GateDecision, Verdict

decision = GateDecision(
    verdict=Verdict.PASS,
    can_publish=True,
    scores={"accuracy": 5, "compliance": 5, "quality": 5},
    min_score=5,
    message="모든 에이전트 통과"
)
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `verdict` | Verdict | O | 최종 판정 |
| `can_publish` | bool | O | 발행 가능 여부 |
| `scores` | Dict[str, int] | O | 에이전트별 점수 |
| `min_score` | int | O | 최소 점수 |
| `message` | str | X | 판정 요약 메시지 |

### Verdict (판정 Enum)

| Verdict | 조건 | 액션 |
|---------|------|------|
| `PASS` | 모든 점수 = 5 | 자동 발행 |
| `BLOCK` | 점수 ≤ 2 | 즉시 거부 |
| `REGENERATE` | 점수 3-4 + 재시도 가능 | 피드백 반영 재번역 |
| `ESCALATE` | 점수 3-4 + 재시도 소진 | REJECTED 처리 |

---

## WorkflowState (워크플로우 상태)

번역 파이프라인의 상태 머신.

| 상태 | 설명 | Terminal |
|------|------|----------|
| `INITIALIZED` | 워크플로우 시작 | - |
| `TRANSLATING` | 번역 진행 중 | - |
| `BACKTRANSLATING` | 역번역 검증 중 | - |
| `EVALUATING` | 에이전트 평가 중 | - |
| `DECIDING` | 게이트 판정 중 | - |
| `REGENERATING` | 재생성 중 | - |
| `PUBLISHED` | 발행 완료 | ✓ |
| `REJECTED` | 거부 | ✓ |
| `FAILED` | 오류 발생 | ✓ |

### 상태 흐름

```
INITIALIZED → TRANSLATING → BACKTRANSLATING → EVALUATING → DECIDING
                                                              │
                         ┌────────────────┬───────────────────┤
                         ▼                ▼                   ▼
                    PUBLISHED       REGENERATING          REJECTED
                                         │
                                         └──► TRANSLATING (loop)
```

### 헬퍼 함수

```python
from src.models import WorkflowState, is_terminal_state, can_transition

is_terminal_state(WorkflowState.PUBLISHED)  # True
can_transition(WorkflowState.DECIDING, WorkflowState.PUBLISHED)  # True
```

---

## JSON 직렬화

모든 모델은 Pydantic v2 기반으로 JSON 직렬화 지원:

```python
# 직렬화
json_str = unit.model_dump_json()

# 역직렬화
unit = TranslationUnit.model_validate_json(json_str)
```
