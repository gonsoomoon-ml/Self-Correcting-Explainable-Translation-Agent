# 데이터 모델 (Data Models)

번역 워크플로우에서 사용하는 Pydantic 데이터 모델을 정의합니다.

## 개요

모든 모델은 Pydantic v2를 사용하여 **타입 안전성**과 **유효성 검증**을 제공합니다.

## 파일 구조

```
src/models/
├── __init__.py              # 모듈 익스포트
├── translation_unit.py      # 번역 입력 단위
├── agent_result.py          # 에이전트 평가 결과
├── gate_decision.py         # 게이트 판정 결과
├── workflow_state.py        # 워크플로우 상태 머신
└── translation_record.py    # 전체 번역 기록
```

## 모델별 설명

### TranslationUnit (번역 단위)

번역 요청의 **입력 스키마**입니다. 단일 FAQ 항목과 번역에 필요한 모든 컨텍스트를 포함합니다.

#### 사용 예시

```python
from src.models import TranslationUnit

unit = TranslationUnit(
    key="IDS_FAQ_SC_ABOUT",
    source_text="ABC 클라우드는 사용자의 ABC 계정과 연동된 서비스입니다.",
    target_lang="en",
    glossary={
        "ABC 클라우드": "ABC Cloud",
        "ABC 계정": "ABC account",
        "동기화": "sync"
    },
    risk_profile="US",
    product="abc_cloud"
)
```

#### 필드 상세

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `key` | str | O | - | FAQ 키 (IDS_FAQ_SC_ABOUT) |
| `source_text` | str | O | - | 원문 (Korean) |
| `source_lang` | str | X | `"ko"` | 소스 언어 코드 |
| `target_lang` | str | O | - | 타겟 언어 코드 (44개) |
| `glossary` | Dict[str, str] | X | `{}` | 용어집 매핑 |
| `risk_profile` | str | X | `"DEFAULT"` | 리스크 프로파일 |
| `style_guide` | Dict[str, str] | X | `{}` | 톤/격식 가이드 |
| `faq_version` | str | X | `"v1.0"` | FAQ 버전 |
| `glossary_version` | str | X | `"v1.0"` | 용어집 버전 |
| `product` | str | X | `"abc_cloud"` | 제품 식별자 |

#### 데이터 흐름

```
data/source/ko_faq.json     data/glossaries/en.yaml     data/risk_profiles/US.yaml
         │                           │                            │
         ▼                           ▼                            ▼
    source_text    +            glossary       +            risk_profile
         │                           │                            │
         └───────────────────────────┴────────────────────────────┘
                                     │
                                     ▼
                            TranslationUnit
                                     │
                                     ▼
                              Translator Agent
```

#### glossary 용어집

용어 일관성을 위해 `source term → target term` 매핑:

```python
glossary = {
    "ABC 클라우드": "ABC Cloud",  # 제품명
    "ABC 계정": "ABC account",    # 계정
    "동기화": "sync",                  # 기능
    "백업": "backup",
    "복원": "restore"
}
```

> `data/glossaries/{lang}.yaml`에서 로드

#### risk_profile 리스크 프로파일

국가별 컴플라이언스 규칙 적용:

| 값 | 설명 | 파일 |
|----|------|------|
| `"US"` | 미국 규정 | `data/risk_profiles/US.yaml` |
| `"DEFAULT"` | 기본 규정 | `data/risk_profiles/DEFAULT.yaml` |

#### target_lang 타겟 언어

`config/languages.yaml`에 정의된 44개 언어 코드:

```python
# 주요 언어 코드
"en"      # English (US)
"en-rGB"  # English (UK)
"ja"      # Japanese
"zh-CN"   # Chinese (Simplified)
"de"      # German
"fr"      # French
# ... 44개
```

### AgentResult (에이전트 결과)

평가 에이전트의 출력을 나타냅니다. **Explainability**를 위한 핵심 모델입니다.

#### Correction (수정 제안)

```python
from src.models import Correction

correction = Correction(
    original="ABC Cloud",           # 문제가 있는 원문
    suggested="ABC Cloud",       # 수정 제안
    reason="용어집에 따라 영문 표기 사용"  # 수정 사유
)
```

#### AgentResult

```python
from src.models import AgentResult, Correction

result = AgentResult(
    agent_name="accuracy",
    reasoning_chain=[
        "Step 1: 의미 보존 확인 - 원문 의미 유지됨",
        "Step 2: 용어집 검증 - 'ABC Cloud' 올바르게 사용",
        "Step 3: 역번역 비교 - 유사도 95%"
    ],
    score=4,
    verdict="pass",
    issues=[],
    corrections=[],
    token_usage={"input_tokens": 500, "output_tokens": 150},
    latency_ms=1200
)
```

#### 필드 상세

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `agent_name` | str | O | 에이전트 이름 (accuracy, compliance, quality) |
| `reasoning_chain` | List[str] | X | Chain-of-Thought 분석 과정 (설명가능성) |
| `score` | int | O | 평가 점수 (0-5, Pydantic 검증) |
| `verdict` | Literal | O | pass, fail, review 중 하나 |
| `issues` | List[str] | X | 발견된 문제점 |
| `corrections` | List[Correction] | X | 수정 제안 |
| `token_usage` | Dict[str, int] | X | 토큰 사용량 (input_tokens, output_tokens) |
| `latency_ms` | int | X | 응답 시간 (밀리초) |

#### reasoning_chain (CoT)

**Explainability**의 핵심. 에이전트가 왜 이 점수를 줬는지 단계별로 기록:

```python
reasoning_chain = [
    "Step 1: 의미 분석 - '동기화'가 'sync'로 정확히 번역됨",
    "Step 2: 용어집 확인 - 5개 용어 중 5개 일치 (100%)",
    "Step 3: 역번역 비교 - 원문과 95% 유사",
    "Step 4: 최종 판단 - 경미한 표현 차이만 존재, 4점"
]
```

#### score ↔ verdict 매핑

`thresholds.yaml`의 기준과 연동:

| score | verdict | 조건 |
|-------|---------|------|
| 5 | `pass` | score == pass_threshold (5) |
| 3-4 | `regenerate` | borderline_scores |
| 0-2 | `fail` | score <= fail_threshold (2) |

```python
# 자동 verdict 계산 예시
def get_verdict(score: int) -> str:
    if score == 5:
        return "pass"
    elif score <= 2:
        return "fail"
    else:
        return "regenerate"  # 3 or 4
```

#### 에이전트별 평가 초점

| agent_name | 평가 항목 |
|------------|-----------|
| `accuracy` | 의미 보존, 용어집 준수, 역번역 비교 |
| `compliance` | 금칙어, 면책조항, 법률 표현 |
| `quality` | 톤/격식, 문화적 적합성, 자연스러움 |

### GateDecision (게이트 판정)

Release Guard의 최종 판정을 나타냅니다. 3개 에이전트 결과를 집계하여 **발행 여부**를 결정합니다.

#### Verdict (판정 Enum)

```python
from src.models import Verdict

class Verdict(str, Enum):
    PASS = "pass"           # 모든 에이전트 = 5점
    BLOCK = "block"         # 어느 에이전트라도 ≤ 2점
    REGENERATE = "regenerate"  # 3-4점 + 재시도 가능
    ESCALATE = "escalate"   # 3-4점 + 재시도 소진 (현재는 REJECTED 처리)
```

#### GateDecision

```python
from src.models import GateDecision, Verdict

decision = GateDecision(
    verdict=Verdict.PASS,
    can_publish=True,
    scores={"accuracy": 5, "compliance": 4, "quality": 4},
    min_score=4,
    avg_score=4.33,
    reasoning_chains={
        "accuracy": ["Step 1: 의미 보존 확인", "Step 2: 용어집 검증"],
        "compliance": ["Step 1: 금칙어 검사 통과"],
        "quality": ["Step 1: US 시장 톤 적합"]
    },
    blocker_agent=None,
    review_agents=[],
    message="모든 에이전트 통과. 발행 가능.",
    agent_agreement_score=0.95,
    total_latency_ms=3500
)
```

#### 필드 상세

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `verdict` | Verdict | O | 최종 판정 |
| `can_publish` | bool | O | 발행 가능 여부 |
| `scores` | Dict[str, int] | O | 에이전트별 점수 |
| `min_score` | int | O | 최소 점수 |
| `avg_score` | float | O | 평균 점수 |
| `reasoning_chains` | Dict[str, List] | X | 에이전트별 CoT (설명가능성) |
| `blocker_agent` | Optional[str] | X | 차단 원인 에이전트 |
| `review_agents` | List[str] | X | 검토 필요 에이전트 (3점) |
| `corrections` | List[dict] | X | 전체 수정 제안 |
| `message` | str | X | 사람이 읽을 수 있는 요약 |
| `agent_agreement_score` | float (0-1) | X | 에이전트 간 일치도 |
| `total_latency_ms` | int | X | 전체 평가 시간 |

#### Verdict 판정 로직

```
┌─────────────────────────────────────────────────────────┐
│                    3개 에이전트 점수                     │
│              accuracy, compliance, quality              │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    min_score ≤ 2   min_score 3-4   모든 점수 = 5
         │               │               │
         ▼               ▼               ▼
      BLOCK         attempt < max?      PASS
         │               │               │
         │          ┌────┴────┐          │
         │          ▼         ▼          │
         │     REGENERATE  REJECTED      │
         │                               │
         ▼                               ▼
    can_publish=False              can_publish=True
```

#### 에이전트 불일치 감지

`agent_agreement_score`로 에이전트 간 일치도 측정:

```python
# thresholds.yaml 기준
disagreement_threshold = 3  # 점수 차이 ≥ 3이면 불일치로 REJECTED

scores = {"accuracy": 5, "compliance": 2, "quality": 4}
max_diff = max(scores.values()) - min(scores.values())  # 5 - 2 = 3

if max_diff >= disagreement_threshold:
    # REJECTED (에이전트 불일치)
    pass
```

#### Verdict별 액션

| Verdict | can_publish | 다음 상태 | 액션 |
|---------|-------------|-----------|------|
| `PASS` | True | PUBLISHED | 자동 발행 (모든 점수 5) |
| `BLOCK` | False | REJECTED | 즉시 차단 (점수 ≤ 2) |
| `REGENERATE` | False | REGENERATING | 피드백과 함께 재번역 (점수 3-4) |
| `ESCALATE` | False | REJECTED | 재시도 소진 시 REJECTED (HITL 미구현) |

### WorkflowState (워크플로우 상태)

번역 파이프라인의 상태 머신을 정의합니다.

#### 상태 목록

| 상태 | 설명 | Terminal |
|------|------|----------|
| `INITIALIZED` | 워크플로우 시작 | - |
| `TRANSLATING` | 번역 진행 중 | - |
| `BACKTRANSLATING` | 역번역 검증 중 | - |
| `EVALUATING` | 3개 에이전트 평가 중 | - |
| `DECIDING` | 게이트 판정 중 | - |
| `REGENERATING` | Maker-Checker 재생성 | - |
| `PENDING_REVIEW` | *(placeholder)* HITL 대기 | - |
| `APPROVED` | *(placeholder)* PM 승인 | - |
| `PUBLISHED` | 발행 완료 | ✓ |
| `REJECTED` | 거부/차단 | ✓ |
| `FAILED` | 오류 발생 | ✓ |

#### 상태 흐름 (현재 구현)

```
INITIALIZED → TRANSLATING → BACKTRANSLATING → EVALUATING → DECIDING
                                                              │
                         ┌────────────────┬───────────────────┤
                         ▼                ▼                   ▼
                    PUBLISHED       REGENERATING          REJECTED
                                         │
                                         ▼
                                    EVALUATING (재평가)
```

> **Note**: `PENDING_REVIEW`, `APPROVED`는 HITL placeholder (미구현)

#### VALID_TRANSITIONS (상태 전이 규칙)

잘못된 상태 전이를 방지하기 위한 규칙 정의:

```python
VALID_TRANSITIONS = {
    INITIALIZED: [TRANSLATING, FAILED],
    TRANSLATING: [BACKTRANSLATING, FAILED],
    BACKTRANSLATING: [EVALUATING, FAILED],
    EVALUATING: [DECIDING, FAILED],
    DECIDING: [PUBLISHED, REGENERATING, REJECTED, FAILED],
    REGENERATING: [EVALUATING, FAILED],
    # Terminal states - 더 이상 전이 불가
    PUBLISHED: [],
    REJECTED: [],
    FAILED: [],
}
```

**필요한 이유:**

| 이유 | 설명 |
|------|------|
| 버그 방지 | 잘못된 상태 전이 즉시 감지 |
| 디버깅 | 오류 발생 위치 명확히 파악 |
| 문서화 | 코드 자체가 워크플로우 명세 |

#### 헬퍼 함수

```python
from src.models import WorkflowState, is_terminal_state, can_transition

# Terminal 상태 확인
is_terminal_state(WorkflowState.PUBLISHED)  # True
is_terminal_state(WorkflowState.EVALUATING)  # False

# 상태 전이 유효성 검증
can_transition(WorkflowState.DECIDING, WorkflowState.PUBLISHED)  # True
can_transition(WorkflowState.PUBLISHED, WorkflowState.TRANSLATING)  # False
```

#### Strands Agent에서 사용

```python
# Strands Agent 워크플로우에서 상태 전이 시 검증
from src.models import can_transition, WorkflowState

def on_state_change(record, new_state: WorkflowState):
    current = record.workflow_state

    if not can_transition(current, new_state):
        raise ValueError(f"Invalid transition: {current} → {new_state}")

    record.workflow_state = new_state
```

**잘못된 전이 예시:**

```python
can_transition(PUBLISHED, TRANSLATING)   # False - Terminal!
can_transition(EVALUATING, PUBLISHED)    # False - DECIDING 거쳐야 함
can_transition(INITIALIZED, PUBLISHED)   # False - 평가 없이 발행 불가
```

---

### TranslationRecord (번역 기록)

번역 워크플로우의 **전체 기록**을 저장합니다. `data/records/`에 JSON으로 저장됩니다.

#### PMReview (placeholder)

```python
class PMReview(BaseModel):
    """Placeholder for future HITL implementation"""
    pass
```

#### TranslationRecord

```python
from src.models import TranslationRecord, WorkflowState

record = TranslationRecord(
    unit=translation_unit,
    candidates=["ABC Cloud is a service."],
    selected_candidate=0,
    backtranslation="ABC 클라우드는 서비스입니다.",
    final_translation="ABC Cloud is a service.",
    agent_results=[accuracy_result, compliance_result, quality_result],
    gate_decision=decision,
    attempt_count=1,
    workflow_state=WorkflowState.PUBLISHED
)
```

#### 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | str (UUID) | 고유 식별자 (자동 생성) |
| `unit` | TranslationUnit | 번역 입력 |
| `candidates` | List[str] | 번역 후보 (1-2개) |
| `selected_candidate` | int | 선택된 후보 인덱스 |
| `backtranslation` | str | 역번역 결과 |
| `final_translation` | str | 최종 번역 |
| `agent_results` | List[AgentResult] | 3개 에이전트 결과 |
| `gate_decision` | GateDecision | 게이트 판정 |
| `attempt_count` | int | 재시도 횟수 |
| `workflow_state` | WorkflowState | 현재 상태 |
| `pm_review` | PMReview | *(placeholder)* |
| `created_at` | datetime | 생성 시각 |
| `updated_at` | datetime | 수정 시각 |
| `published_at` | datetime | 발행 시각 |
| `metadata` | Dict | 추가 메타데이터 |

#### 저장 위치

```
data/records/
└── {uuid}.json    # TranslationRecord JSON
```

#### Explainability

`TranslationRecord`로 **왜 이 번역이 승인/거부되었는지** 추적:

```python
# 기록 로드
record = TranslationRecord.model_validate_json(json_str)

# 판정 사유 확인
print(record.gate_decision.verdict)  # "pass" or "block"
print(record.gate_decision.message)  # "모든 에이전트 통과"

# 에이전트별 CoT 확인
for result in record.agent_results:
    print(f"{result.agent_name}: {result.score}점")
    for step in result.reasoning_chain:
        print(f"  - {step}")
```

## 사용 예시

```python
from src.models import (
    TranslationUnit,
    AgentResult,
    GateDecision,
    Verdict,
    WorkflowState,
    TranslationRecord
)

# 1. 번역 단위 생성
unit = TranslationUnit(
    key="IDS_FAQ_SC_ABOUT",
    source_text="ABC 클라우드는 서비스입니다.",
    target_lang="en-rUS"
)

# 2. 에이전트 결과 수집
results = [accuracy_result, compliance_result, quality_result]

# 3. 게이트 판정
if all(r.score == 5 for r in results):
    decision = GateDecision(
        verdict=Verdict.PASS,
        can_publish=True,
        scores={r.agent_name: r.score for r in results},
        ...
    )

# 4. 기록 저장
record = TranslationRecord(
    unit=unit,
    agent_results=results,
    gate_decision=decision,
    ...
)
```

## JSON 직렬화

모든 모델은 Pydantic이므로 JSON 직렬화/역직렬화가 가능합니다:

```python
# 직렬화
json_str = unit.model_dump_json()

# 역직렬화
unit = TranslationUnit.model_validate_json(json_str)
```
