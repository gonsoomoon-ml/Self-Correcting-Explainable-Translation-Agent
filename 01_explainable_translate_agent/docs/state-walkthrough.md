# State Walkthrough 가이드

워크플로우 실행 중 State 객체가 어떻게 변화하는지 상세히 설명합니다.

## 왜 State Walkthrough인가?

| 문제 | 영향 |
|------|------|
| **State 구조 이해 어려움** | 디버깅 시 어떤 필드를 확인해야 할지 모름 |
| **노드 간 데이터 흐름 불명확** | 새 노드 추가 시 어떤 데이터가 필요한지 파악 어려움 |
| **재생성 루프 복잡성** | attempt_count, feedback 등 루프 관련 필드 이해 부족 |

**State Walkthrough 해결책:**

| 기능 | 효과 |
|------|------|
| **단계별 State 스냅샷** | 각 노드 실행 후 State 변화 명시 |
| **추가/변경 필드 표시** | ✅ 마크로 새로 추가된 필드 강조 |
| **실제 데이터 예시** | 추상적 설명 대신 구체적 값으로 이해 |

---

## State 흐름 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STATE 변화 흐름                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INIT                translate_node         backtranslate_node              │
│  ─────────────────►  ──────────────────►   ─────────────────────►           │
│  • unit              + translation_result   + backtranslation_result        │
│  • attempt_count=1   • TRANSLATING          • BACKTRANSLATING               │
│                                                                              │
│  evaluate_node                decide_node                                    │
│  ─────────────────────────►   ───────────────────────────────►              │
│  + agent_results (×3)         + gate_decision                               │
│  + eval_start_time            + attempt_history                             │
│  • EVALUATING                 • DECIDING                                    │
│                                                                              │
│         ┌─────────────────────────────────────────────────────┐             │
│         │                    VERDICT?                          │             │
│         └────────────┬──────────────┬─────────────────────────┘             │
│                      │              │                                        │
│         ┌────────────▼──┐    ┌──────▼──────┐                                │
│         │  REGENERATE   │    │ PASS/BLOCK  │                                │
│         └───────┬───────┘    └──────┬──────┘                                │
│                 │                   │                                        │
│    regenerate_node              finalize_node                               │
│    ───────────────►             ──────────────►                             │
│    + feedback                   + final_translation                         │
│    • attempt_count++            • PUBLISHED / REJECTED                      │
│    • REGENERATING               └───────────────────                        │
│         │                                                                    │
│         └──────────────► translate_node (loop back)                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 단계별 State 변화

### 초기 상태 (builder.py에서 생성)

```python
state = {
    "unit": TranslationUnit(
        key="faq_001",
        source_text="ABC 클라우드에서 데이터를 백업하세요.",
        source_lang="ko",
        target_lang="en-rUS",
        glossary={"ABC 클라우드": "ABC Cloud"}
    ),
    "attempt_count": 1,
    "num_candidates": 1,
    "max_regenerations": 1,
    "workflow_state": WorkflowState.INITIALIZED,
    "created_at": datetime(2025, 1, 5, 10, 0, 0)
}
```

---

### Step 1: `translate_node` 실행 후

```python
state = {
    # 기존 유지
    "unit": TranslationUnit(...),
    "attempt_count": 1,
    "num_candidates": 1,
    "max_regenerations": 1,
    "created_at": datetime(...),

    # ✅ 추가됨
    "translation_result": TranslationResult(
        translation="Back up your data on ABC Cloud.",
        candidates=["Back up your data on ABC Cloud."],
        reasoning_chain=["용어집 적용: ABC 클라우드 → ABC Cloud", ...],
        latency_ms=1523,
        token_usage={"input_tokens": 450, "output_tokens": 89}
    ),
    "workflow_state": WorkflowState.TRANSLATING  # ✅ 변경됨
}
```

---

### Step 2: `backtranslate_node` 실행 후

```python
state = {
    # 기존 유지
    "unit": TranslationUnit(...),
    "attempt_count": 1,
    "translation_result": TranslationResult(...),
    ...

    # ✅ 추가됨
    "backtranslation_result": BacktranslationResult(
        backtranslation="ABC 클라우드에서 데이터를 백업하세요.",
        latency_ms=892,
        token_usage={"input_tokens": 120, "output_tokens": 45}
    ),
    "workflow_state": WorkflowState.BACKTRANSLATING  # ✅ 변경됨
}
```

---

### Step 3: `evaluate_node` 실행 후 (3 에이전트 병렬)

```python
state = {
    # 기존 유지
    "unit": TranslationUnit(...),
    "translation_result": TranslationResult(...),
    "backtranslation_result": BacktranslationResult(...),
    ...

    # ✅ 추가됨
    "agent_results": [
        AgentResult(
            agent_name="accuracy",
            score=5,
            verdict="pass",
            reasoning_chain=["역번역 비교: 원문과 일치", "용어집 준수 확인"],
            issues=[],
            corrections=[],
            latency_ms=1102
        ),
        AgentResult(
            agent_name="compliance",
            score=3,                    # ⚠️ 경계 점수
            verdict="review",
            reasoning_chain=["'backup' 문구 발견", "면책조항 누락 확인"],
            issues=["데이터 백업 면책조항 누락"],
            corrections=[
                Correction(
                    original="Back up your data on ABC Cloud.",
                    suggested="Back up your data on ABC Cloud. Note: Backup may not include all content.",
                    reason="US.yaml required_disclaimers.data_backup"
                )
            ],
            latency_ms=1245
        ),
        AgentResult(
            agent_name="quality",
            score=5,
            verdict="pass",
            reasoning_chain=["자연스러운 영어 표현", "용어집 제약 인식"],
            issues=[],
            corrections=[],
            latency_ms=987
        )
    ],
    "eval_start_time": datetime(2025, 1, 5, 10, 0, 3),
    "workflow_state": WorkflowState.EVALUATING  # ✅ 변경됨
}
```

---

### Step 4: `decide_node` 실행 후 (SOP 판정)

```python
state = {
    # 기존 유지
    ...
    "agent_results": [...],

    # ✅ 추가됨
    "gate_decision": GateDecision(
        verdict=Verdict.REGENERATE,     # 3점이 있어서 재생성
        scores={"accuracy": 5, "compliance": 3, "quality": 5},
        can_publish=False,
        message="compliance 에이전트 점수가 기준 미달입니다.",
        review_agents=["compliance"]
    ),
    "attempt_history": [
        {
            "attempt": 1,
            "verdict": "regenerate",
            "scores": {"accuracy": 5, "compliance": 3, "quality": 5},
            "message": "compliance 에이전트 점수가 기준 미달입니다.",
            "review_agents": ["compliance"],
            "issues": {
                "compliance": ["데이터 백업 면책조항 누락"]
            },
            "corrections": {
                "compliance": [{
                    "original": "Back up your data on ABC Cloud.",
                    "suggested": "Back up your data on ABC Cloud. Note: ...",
                    "reason": "US.yaml required_disclaimers.data_backup"
                }]
            }
        }
    ],
    "workflow_state": WorkflowState.DECIDING  # ✅ 변경됨
}
```

---

### Step 5: `regenerate_node` 실행 후 (재생성 준비)

```python
state = {
    # 기존 유지
    ...
    "gate_decision": GateDecision(verdict=REGENERATE, ...),
    "attempt_history": [...],

    # ✅ 변경됨
    "attempt_count": 2,  # 1 → 2

    # ✅ 추가됨
    "feedback": """
이전 번역의 문제점:
- compliance: 데이터 백업 면책조항 누락

수정 제안:
- 원문: "Back up your data on ABC Cloud."
  제안: "Back up your data on ABC Cloud. Note: Backup may not include all content."
  이유: US.yaml required_disclaimers.data_backup

위 문제를 해결하여 다시 번역해주세요.
""",
    "workflow_state": WorkflowState.REGENERATING  # ✅ 변경됨
}
```

---

### Step 6: `translate_node` 재실행 (feedback 반영)

```python
state = {
    ...
    "attempt_count": 2,
    "feedback": "이전 번역의 문제점: ...",

    # ✅ 덮어쓰기됨
    "translation_result": TranslationResult(
        translation="Back up your data on ABC Cloud. Note: Backup may not include all content.",
        candidates=["Back up your data on ABC Cloud. Note: ..."],
        reasoning_chain=[
            "피드백 반영: 면책조항 추가",
            "용어집 적용: ABC 클라우드 → ABC Cloud"
        ],
        latency_ms=1634,
        token_usage={...}
    ),
    "workflow_state": WorkflowState.TRANSLATING
}
```

---

### Step 7-8: 재평가 후 PASS

```python
state = {
    ...
    "attempt_count": 2,

    "agent_results": [
        AgentResult(agent_name="accuracy", score=5, ...),
        AgentResult(agent_name="compliance", score=5, ...),  # ✅ 3 → 5
        AgentResult(agent_name="quality", score=5, ...)
    ],

    "gate_decision": GateDecision(
        verdict=Verdict.PASS,           # ✅ REGENERATE → PASS
        scores={"accuracy": 5, "compliance": 5, "quality": 5},
        can_publish=True,
        message="모든 에이전트 점수가 기준을 충족합니다."
    ),

    "attempt_history": [
        {"attempt": 1, "verdict": "regenerate", ...},
        {"attempt": 2, "verdict": "pass", ...}  # ✅ 추가됨
    ]
}
```

---

### Step 9: `finalize_node` 실행 후 (최종)

```python
state = {
    # 전체 컨텍스트
    "unit": TranslationUnit(...),
    "attempt_count": 2,
    "num_candidates": 1,
    "max_regenerations": 1,
    "created_at": datetime(...),

    # 번역 결과
    "translation_result": TranslationResult(...),
    "backtranslation_result": BacktranslationResult(...),

    # 평가 결과
    "agent_results": [...],
    "eval_start_time": datetime(...),

    # 판정 결과
    "gate_decision": GateDecision(verdict=PASS, ...),
    "attempt_history": [{...}, {...}],

    # ✅ 최종 추가
    "final_translation": "Back up your data on ABC Cloud. Note: Backup may not include all content.",
    "workflow_state": WorkflowState.PUBLISHED,  # ✅ 최종 상태

    # 메트릭 (builder.py에서 추가)
    "metrics": WorkflowMetrics(
        total_latency_ms=8234,
        translation_latency_ms=3157,
        backtranslation_latency_ms=1784,
        evaluation_latency_ms=3293,
        attempt_count=2,
        token_usage={"input": 2341, "output": 567, ...}
    )
}
```

---

## State 필드 요약

### 초기 필드 (builder.py)

| 필드 | 타입 | 설명 |
|------|------|------|
| `unit` | TranslationUnit | 번역 대상 (원문, 언어, 용어집 등) |
| `attempt_count` | int | 현재 시도 횟수 |
| `num_candidates` | int | 생성할 번역 후보 수 |
| `max_regenerations` | int | 최대 재생성 횟수 |
| `workflow_state` | WorkflowState | 현재 워크플로우 상태 |
| `created_at` | datetime | 워크플로우 시작 시간 |

### 노드별 추가 필드

| 노드 | 추가 필드 | 타입 |
|------|-----------|------|
| `translate_node` | `translation_result` | TranslationResult |
| `backtranslate_node` | `backtranslation_result` | BacktranslationResult |
| `evaluate_node` | `agent_results`, `eval_start_time` | List[AgentResult], datetime |
| `decide_node` | `gate_decision`, `attempt_history` | GateDecision, List[dict] |
| `regenerate_node` | `feedback` | str |
| `finalize_node` | `final_translation` | str |

### 최종 필드 (builder.py)

| 필드 | 타입 | 설명 |
|------|------|------|
| `metrics` | WorkflowMetrics | 전체 메트릭 (latency, tokens) |
| `error` | str (optional) | 실패 시 에러 메시지 |

---

## WorkflowState 전이

```
INITIALIZED
     │
     ▼
TRANSLATING ◄────────────────────────┐
     │                               │
     ▼                               │
BACKTRANSLATING                      │
     │                               │
     ▼                               │
EVALUATING                           │
     │                               │
     ▼                               │
DECIDING ─────────────► REGENERATING ┘
     │
     ▼
┌────┴────┐
│         │
▼         ▼
PUBLISHED REJECTED
          │
          ▼
     PENDING_REVIEW
```

---

## 디버깅 팁

### 특정 시도의 이슈 확인

```python
# attempt_history에서 특정 시도의 문제점 확인
for attempt in state["attempt_history"]:
    print(f"시도 {attempt['attempt']}: {attempt['verdict']}")
    for agent, issues in attempt["issues"].items():
        print(f"  - {agent}: {issues}")
```

### 재생성 피드백 확인

```python
# 번역기에 전달된 피드백 확인
if "feedback" in state:
    print(state["feedback"])
```

### 점수 변화 추적

```python
# 시도별 점수 변화 확인
for attempt in state["attempt_history"]:
    print(f"시도 {attempt['attempt']}: {attempt['scores']}")
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/graph/builder.py` | 초기 State 생성, 메트릭 계산 |
| `src/graph/nodes.py` | 각 노드에서 State 업데이트 |
| `src/models/workflow_state.py` | WorkflowState enum 정의 |
| `sops/evaluation_gate.py` | GateDecision 생성 |
| `sops/regeneration.py` | feedback 생성 |
