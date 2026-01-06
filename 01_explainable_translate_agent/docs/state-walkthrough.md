# State Walkthrough 가이드

워크플로우 실행 중 State 객체가 어떻게 변화하는지 설명합니다.

## State 흐름 다이어그램

```
INIT                translate_node         backtranslate_node
─────────────────►  ──────────────────►   ─────────────────────►
• unit              + translation_result   + backtranslation_result
• attempt_count=1

evaluate_node                decide_node
─────────────────────────►   ───────────────────────────────►
+ agent_results (×3)         + gate_decision
                             + attempt_history

       ┌─────────────────────────────────────────────────────┐
       │                    VERDICT?                          │
       └────────────┬──────────────┬─────────────────────────┘
                    │              │
       ┌────────────▼──┐    ┌──────▼──────┐
       │  REGENERATE   │    │ PASS/BLOCK  │
       └───────┬───────┘    └──────┬──────┘
               │                   │
  regenerate_node              finalize_node
  ───────────────►             ──────────────►
  + feedback                   + final_translation
  • attempt_count++            • PUBLISHED / REJECTED
       │
       └──────────────► translate_node (loop back)
```

---

## 단계별 State 변화

### 초기 상태

```python
state = {
    "unit": TranslationUnit(
        key="IDS_FAQ_001",
        source_text="ABC 클라우드에서 동기화가 되지 않습니다.",
        target_lang="en-rUS",
        product="abc_cloud"
    ),
    "attempt_count": 1,
    "max_regenerations": 1,
    "workflow_state": WorkflowState.INITIALIZED
}
```

### translate_node 실행 후

```python
# ✅ 추가됨
"translation_result": TranslationResult(
    translation="Sync is not working on ABC Cloud.",
    candidates=["Sync is not working on ABC Cloud."],
    latency_ms=1523,
    token_usage={"input_tokens": 450, "output_tokens": 89}
)
```

### backtranslate_node 실행 후

```python
# ✅ 추가됨
"backtranslation_result": BacktranslationResult(
    backtranslation="ABC 클라우드에서 동기화가 되지 않습니다.",
    latency_ms=892
)
```

### evaluate_node 실행 후

```python
# ✅ 추가됨
"agent_results": [
    AgentResult(agent_name="accuracy", score=5, issues=[], corrections=[]),
    AgentResult(agent_name="compliance", score=3, issues=["면책조항 누락"], corrections=[...]),
    AgentResult(agent_name="quality", score=5, issues=[], corrections=[])
]
```

### decide_node 실행 후

```python
# ✅ 추가됨
"gate_decision": GateDecision(
    verdict=Verdict.REGENERATE,  # 3점이 있어서 재생성
    scores={"accuracy": 5, "compliance": 3, "quality": 5},
    can_publish=False
),
"attempt_history": [
    {"attempt": 1, "verdict": "regenerate", "scores": {...}, "issues": {...}}
]
```

### regenerate_node 실행 후

```python
# ✅ 변경됨
"attempt_count": 2,  # 1 → 2

# ✅ 추가됨
"feedback": """
이전 번역의 문제점:
- compliance: 면책조항 누락

수정 제안:
- "Back up your data..." → "Back up your data... Note: Backup may not include all content."

위 문제를 해결하여 다시 번역해주세요.
"""
```

### 재생성 후 PASS → finalize_node

```python
# 재평가 후 모든 점수 5
"agent_results": [
    AgentResult(agent_name="accuracy", score=5, ...),
    AgentResult(agent_name="compliance", score=5, ...),  # ✅ 3 → 5
    AgentResult(agent_name="quality", score=5, ...)
],
"gate_decision": GateDecision(verdict=Verdict.PASS, ...),

# ✅ 최종 추가
"final_translation": "Back up your data on ABC Cloud. Note: Backup may not include all content.",
"workflow_state": WorkflowState.PUBLISHED,

# 메트릭
"metrics": WorkflowMetrics(
    total_latency_ms=8234,
    attempt_count=2,
    token_usage={"input": 2341, "output": 567}
)
```

---

## State 필드 요약

### 초기 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `unit` | TranslationUnit | 번역 단위 (원문, 언어, product → glossary/style_guide/risk_profile 자동 로드) |
| `attempt_count` | int | 현재 시도 횟수 |
| `max_regenerations` | int | 최대 재생성 횟수 |
| `workflow_state` | WorkflowState | 현재 워크플로우 상태 |

### 노드별 추가 필드

| 노드 | 추가 필드 | 타입 |
|------|-----------|------|
| `translate_node` | `translation_result` | TranslationResult |
| `backtranslate_node` | `backtranslation_result` | BacktranslationResult |
| `evaluate_node` | `agent_results` | List[AgentResult] |
| `decide_node` | `gate_decision`, `attempt_history` | GateDecision, List[dict] |
| `regenerate_node` | `feedback` | str |
| `finalize_node` | `final_translation` | str |

### 최종 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `metrics` | WorkflowMetrics | 전체 메트릭 (latency, tokens) |
| `error` | str (optional) | 실패 시 에러 메시지 |

---

## 상태 관리 동작 원리 (WorkflowStateManager)

### 왜 글로벌 상태인가?

Strands GraphBuilder에서 노드는 `task` 파라미터만 받습니다. 노드 간 데이터 공유를 위해 **글로벌 상태 저장소** 패턴을 사용합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    글로벌 상태 저장소                         │
│  _workflow_states = {                                       │
│      "uuid-1": { unit, translation_result, ... },          │
│      "uuid-2": { unit, translation_result, ... },          │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
        ▲               ▲               ▲
        │               │               │
   translate_node  backtranslate   evaluate_node
        │               │               │
        └───────────────┴───────────────┘
              get_workflow_state()로 접근
```

### 글로벌 변수

```python
_workflow_states: Dict[str, Dict[str, Any]] = {}  # 워크플로우ID → 상태
_states_lock = threading.Lock()                    # 스레드 안전 보장
_current_workflow_id: Optional[str] = None         # 현재 활성 워크플로우
```

### 실행 흐름

```
1. 워크플로우 시작
   ┌──────────────────────────────────────────────────────────┐
   │ with workflow_context(unit, config) as workflow_id:      │
   │                          │                               │
   │                          ▼                               │
   │           WorkflowStateManager.create_workflow()         │
   │                          │                               │
   │                          ▼                               │
   │           _workflow_states["uuid-xxx"] = {               │
   │               "unit": unit,                              │
   │               "attempt_count": 1,                        │
   │               "workflow_state": INITIALIZED,             │
   │               "token_usage": {...}                       │
   │           }                                              │
   │           _current_workflow_id = "uuid-xxx"              │
   └──────────────────────────────────────────────────────────┘

2. 노드 실행 (translate_node)
   ┌──────────────────────────────────────────────────────────┐
   │ async def translate_node(task=None, **kwargs):           │
   │     state = get_workflow_state()  # 글로벌 상태 가져오기   │
   │                   │                                      │
   │                   ▼                                      │
   │     _workflow_states[_current_workflow_id] 반환          │
   │                   │                                      │
   │     unit = state["unit"]                                 │
   │     result = await translate(...)                        │
   │     state["translation_result"] = result  # 직접 수정     │
   └──────────────────────────────────────────────────────────┘

3. 다음 노드 (backtranslate_node)
   ┌──────────────────────────────────────────────────────────┐
   │ async def backtranslate_node(task=None, **kwargs):       │
   │     state = get_workflow_state()                         │
   │     translation = state["translation_result"]  # 이전 결과│
   │     ...                                                  │
   └──────────────────────────────────────────────────────────┘

4. 워크플로우 종료
   ┌──────────────────────────────────────────────────────────┐
   │ # with 블록 종료 시 자동 실행                              │
   │ WorkflowStateManager.cleanup(workflow_id)                │
   │                   │                                      │
   │                   ▼                                      │
   │ final_state = _workflow_states.pop("uuid-xxx")          │
   │ _current_workflow_id = None                              │
   │ return final_state                                       │
   └──────────────────────────────────────────────────────────┘
```

### 주요 함수

| 함수 | 설명 |
|------|------|
| `workflow_context(unit, config)` | 컨텍스트 매니저 (생성→정리 자동) |
| `get_workflow_state(workflow_id?)` | 현재 상태 가져오기 (직접 수정 가능) |
| `update_workflow_state(updates)` | 상태 업데이트 |
| `should_regenerate_from_state()` | 재생성 조건 확인 (GraphBuilder 조건 함수용) |
| `should_finalize_from_state()` | 최종화 조건 확인 (GraphBuilder 조건 함수용) |

### 사용 예시

```python
from src.utils.workflow_state import workflow_context, get_workflow_state

# 컨텍스트 매니저 사용 (권장)
with workflow_context(unit, config) as workflow_id:
    result = await graph.invoke_async(task)
    final_state = get_workflow_state(workflow_id)
# with 블록 종료 시 자동 cleanup

# 노드 내에서 상태 접근
async def translate_node(task=None, **kwargs):
    state = get_workflow_state()
    unit = state["unit"]
    # ... 처리 ...
    state["translation_result"] = result
    return {"status": "completed"}
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/graph/builder.py` | GraphBuilder 워크플로우 정의, 메트릭 계산 |
| `src/graph/nodes.py` | 각 노드에서 State 업데이트 |
| `src/utils/workflow_state.py` | WorkflowStateManager, 글로벌 상태 관리 |
| `sops/evaluation_gate.py` | GateDecision 생성 |
| `sops/regeneration.py` | feedback 생성 |
