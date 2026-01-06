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
        key="faq_001",
        source_text="ABC 클라우드에서 데이터를 백업하세요.",
        source_lang="ko",
        target_lang="en-rUS",
        glossary={"ABC 클라우드": "ABC Cloud"},
        risk_profile="US",
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
    translation="Back up your data on ABC Cloud.",
    candidates=["Back up your data on ABC Cloud."],
    latency_ms=1523,
    token_usage={"input_tokens": 450, "output_tokens": 89}
)
```

### backtranslate_node 실행 후

```python
# ✅ 추가됨
"backtranslation_result": BacktranslationResult(
    backtranslation="ABC 클라우드에서 데이터를 백업하세요.",
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
| `unit` | TranslationUnit | 번역 단위 (원문, 언어, 용어집, 리스크 프로파일 등) |
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

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/graph/builder.py` | GraphBuilder 워크플로우 정의, 메트릭 계산 |
| `src/graph/nodes.py` | 각 노드에서 State 업데이트 |
| `src/utils/workflow_state.py` | WorkflowStateManager, 상태 관리 |
| `sops/evaluation_gate.py` | GateDecision 생성 |
| `sops/regeneration.py` | feedback 생성 |
