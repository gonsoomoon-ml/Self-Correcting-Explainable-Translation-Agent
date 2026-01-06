# Graph - 워크플로우 오케스트레이션

번역 파이프라인을 **Strands GraphBuilder**로 오케스트레이션하는 모듈입니다.

## 개요

이 모듈은 FAQ 번역의 전체 워크플로우를 관리합니다:
1. **번역** - 원문을 대상 언어로 번역
2. **역번역** - 번역 검증을 위한 역번역
3. **평가** - 3개 에이전트가 병렬로 품질 평가
4. **판정** - 발행/재생성/거부 결정
5. **재생성** (필요시) - 피드백 반영하여 재번역

---

## 파이프라인 흐름

```
                              ┌──────────┐
                              │ GLOSSARY │ (용어 제약)
                              └────┬─────┘
                                   │
┌──────────────────────────────────┼──────────────────────────────────────────┐
│                              번역 파이프라인                                  │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   ▼
    [1] 번역        [2] 역번역       [3] 평가         [4] 판정        [5] 최종
   ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
   │translate│────▶│  back  │────▶│evaluate│────▶│ decide │────▶│finalize│
   │  _node │     │translate│     │ _node  │     │ _node  │     │ _node  │
   └────────┘     │ _node  │     └────────┘     └────────┘     └────────┘
       ▲          └────────┘          │              │              │
       │                              │              ▼              ▼
       │                         ┌────┴────┐   ┌─────────┐    ┌─────────┐
       │                         │ 3 Agent │   │   SOP   │    │ 발행    │
       │                         │ 병렬실행 │   │ (정책)  │    │ 거부    │
       │                         └─────────┘   └────┬────┘    │ 검수대기 │
       │                                            │         └─────────┘
       └────────────────────────────────────────────┘
                        (Maker-Checker 루프)
```

---

## 노드 상세 (nodes.py)

### 1. `translate_node` - 번역 노드

원문을 대상 언어로 번역합니다.

```python
state = await translate_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `unit` | `TranslationUnit` | ✅ | 번역 단위 (원문, product) |
| `feedback` | `str` | ❌ | 재생성시 피드백 |
| `num_candidates` | `int` | ❌ | 후보 수 (기본: 1) |

**출력 상태:**
| 키 | 타입 | 설명 |
|----|------|------|
| `translation_result` | `TranslationResult` | 번역 결과 |
| `workflow_state` | `TRANSLATING` | 상태 업데이트 |

---

### 2. `backtranslate_node` - 역번역 노드

번역 결과를 원본 언어로 다시 번역합니다.
정확성 평가에서 의미 보존 검증에 사용됩니다.

```python
state = await backtranslate_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `translation_result` | `TranslationResult` | ✅ | 번역 결과 |
| `unit` | `TranslationUnit` | ✅ | 언어 정보 (source_lang, target_lang) |

**출력 상태:**
| 키 | 타입 | 설명 |
|----|------|------|
| `backtranslation_result` | `BacktranslationResult` | 역번역 결과 |
| `workflow_state` | `BACKTRANSLATING` | 상태 업데이트 |

---

### 3. `evaluate_node` - 평가 노드

3개 평가 에이전트를 **병렬**로 실행합니다:
- **Accuracy** - 의미 충실도, 용어집 적용
- **Compliance** - 규정 준수, 금칙어 검사
- **Quality** - 유창성, 톤, 문화적 적합성

```python
state = await evaluate_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `unit` | `TranslationUnit` | ✅ | 원문, glossary, risk_profile (자동 로드) |
| `translation_result` | `TranslationResult` | ✅ | 번역 결과 |
| `backtranslation_result` | `BacktranslationResult` | ✅ | 역번역 결과 |

**출력 상태:**
| 키 | 타입 | 설명 |
|----|------|------|
| `agent_results` | `List[AgentResult]` | 3개 평가 결과 |
| `eval_start_time` | `datetime` | 평가 시작 시간 |
| `workflow_state` | `EVALUATING` | 상태 업데이트 |

**내부 동작:**
```python
# 3개 에이전트 동시 실행
results = await asyncio.gather(
    evaluate_accuracy(...),
    evaluate_compliance(...),
    evaluate_quality(...)
)
```

---

### 4. `decide_node` - 판정 노드

Release Guard SOP를 실행하여 최종 판정을 결정합니다.

```python
state = await decide_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `agent_results` | `List[AgentResult]` | ✅ | 평가 결과 |
| `attempt_count` | `int` | ❌ | 시도 횟수 (기본: 1) |

**출력 상태:**
| 키 | 타입 | 설명 |
|----|------|------|
| `gate_decision` | `GateDecision` | 판정 결과 |
| `workflow_state` | `DECIDING` | 상태 업데이트 |

**판정 규칙:**
| 조건 | Verdict | 의미 |
|------|---------|------|
| 모든 점수 = 5 | `PASS` | 발행 가능 |
| 어느 점수 ≤ 2 | `BLOCK` | 즉시 거부 |
| 점수 3-4, 재시도 가능 | `REGENERATE` | 재생성 |
| 점수 3-4, 재시도 소진 | `REJECTED` | 거부 |
| 점수 차이 ≥ 3 | `REJECTED` | 에이전트 불일치 |

---

### 5. `regenerate_node` - 재생성 준비 노드

평가 결과에서 피드백을 수집하고 번역기에 전달할 형태로 포맷합니다.

```python
state = await regenerate_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `agent_results` | `List[AgentResult]` | ✅ | 평가 결과 |
| `translation_result` | `TranslationResult` | ✅ | 이전 번역 |
| `attempt_count` | `int` | ✅ | 현재 시도 횟수 |

**출력 상태:**
| 키 | 타입 | 설명 |
|----|------|------|
| `feedback` | `str` | 포맷된 피드백 |
| `attempt_count` | `int` | 증가된 시도 횟수 |
| `workflow_state` | `REGENERATING` | 상태 업데이트 |

**생성되는 피드백 예시:**
```xml
<previous_feedback>
이전 번역에서 다음 문제가 발견되었습니다:

**발견된 문제:**
1. 용어집의 'ABC Cloud' 대신 'ABC Company cloud' 사용

**수정 제안:**
- 'ABC Company cloud' → 'ABC Cloud'
  사유: 용어집 표준 용어

위 문제점을 피하여 새로운 번역을 생성하세요.
</previous_feedback>
```

---

### 6. `finalize_node` - 최종화 노드

판정 결과에 따라 최종 워크플로우 상태를 설정합니다.

```python
state = await finalize_node(state)
```

**입력 상태:**
| 키 | 타입 | 필수 | 설명 |
|----|------|------|------|
| `gate_decision` | `GateDecision` | ✅ | 판정 결과 |
| `translation_result` | `TranslationResult` | ✅ | 번역 결과 |

**출력 상태 (Verdict에 따라):**
| Verdict | workflow_state | 추가 출력 |
|---------|----------------|-----------|
| `PASS` | `PUBLISHED` | `final_translation` 설정 |
| `BLOCK` | `REJECTED` | - |
| `ESCALATE` | `PENDING_REVIEW` | - |

---

## 그래프 빌더 상세 (builder.py)

`TranslationWorkflowGraphV2`는 **Strands GraphBuilder**를 사용하여 노드들을 오케스트레이션하는 메인 컨트롤러입니다.

### 클래스 구조

```python
class TranslationWorkflowGraphV2:
    def __init__(self, config: TranslationWorkflowConfig = None)
    async def run(self, unit: TranslationUnit) -> Dict[str, Any]
```

### GraphBuilder 그래프 빌드

```python
def build_translation_graph(config: TranslationWorkflowConfig = None):
    builder = GraphBuilder()

    # 노드 등록 (FunctionNode로 래핑)
    builder.add_node(FunctionNode(translate_node, "translate"), "translate")
    builder.add_node(FunctionNode(backtranslate_node, "backtranslate"), "backtranslate")
    builder.add_node(FunctionNode(evaluate_node, "evaluate"), "evaluate")
    builder.add_node(FunctionNode(decide_node, "decide"), "decide")
    builder.add_node(FunctionNode(regenerate_node, "regenerate"), "regenerate")
    builder.add_node(FunctionNode(finalize_node, "finalize"), "finalize")

    # 엣지 정의
    builder.set_entry_point("translate")
    builder.add_edge("translate", "backtranslate")
    builder.add_edge("backtranslate", "evaluate")
    builder.add_edge("evaluate", "decide")
    builder.add_edge("decide", "finalize", condition=should_finalize)
    builder.add_edge("decide", "regenerate", condition=should_regenerate)
    builder.add_edge("regenerate", "translate")

    return builder.build()
```

### `run()` 메서드 실행 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                        run(unit)                                 │
├─────────────────────────────────────────────────────────────────┤
│  1. WorkflowStateManager로 상태 생성                             │
│     workflow_id = state_manager.create_workflow(unit, config)   │
│                                                                  │
│  2. GraphBuilder.invoke_async() 호출                             │
│                          ↓                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │            GraphBuilder 자동 실행 (선언적 그래프)         │    │
│  │                                                          │    │
│  │  translate → backtranslate → evaluate → decide           │    │
│  │                                           ↓              │    │
│  │                          ┌────────────────┼──────────┐   │    │
│  │                          ↓                ↓          │   │    │
│  │                      finalize        regenerate      │   │    │
│  │                   (PASS/BLOCK)       (loop back)     │   │    │
│  │                                           ↓          │   │    │
│  │                                       translate      │   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  3. 메트릭 계산 → state["metrics"]                               │
│                                                                  │
│  4. return state                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 조건 함수 (GraphBuilder 조건부 엣지용)

```python
def should_regenerate(_) -> bool:
    """재생성 조건: verdict == REGENERATE && attempt <= max_regen"""
    state = get_workflow_state()
    decision = state.get("gate_decision")
    max_regen = state.get("max_regenerations", 1)
    attempt = state.get("attempt_count", 1)

    if decision and decision.verdict == Verdict.REGENERATE:
        return attempt <= max_regen
    return False

def should_finalize(_) -> bool:
    """최종화 조건: not should_regenerate"""
    return not should_regenerate(_)
```

**참고:** GraphBuilder에서는 `condition` 파라미터로 조건부 분기를 선언적으로 정의합니다:
```python
builder.add_edge("decide", "finalize", condition=should_finalize)
builder.add_edge("decide", "regenerate", condition=should_regenerate)
```

### Maker-Checker 루프 예시

```
시도 1:
  translate → backtranslate → evaluate → decide
                                           ↓
                              verdict = REGENERATE (점수 3-4)
                                           ↓
                              regenerate (피드백 수집)
                                           ↓
                              attempt_count = 2
                                           ↓
                              continue (루프 반복)

시도 2:
  translate(피드백 반영) → backtranslate → evaluate → decide
                                                        ↓
                                           verdict = PASS (모든 점수 5)
                                                        ↓
                                           finalize → PUBLISHED
                                                        ↓
                                                      break
```

### 메트릭 수집 (`WorkflowMetrics`)

```python
@dataclass
class WorkflowMetrics:
    total_latency_ms: int        # 전체 실행 시간
    translation_latency_ms: int  # 번역 시간
    backtranslation_latency_ms: int  # 역번역 시간
    evaluation_latency_ms: int   # 평가 시간 (3개 합계)
    attempt_count: int           # 시도 횟수
    token_usage: Dict[str, int]  # {"input": ..., "output": ...}
```

**메트릭 접근:**
```python
result = await graph.run(unit)
metrics = result["metrics"]

print(f"총 시간: {metrics.total_latency_ms}ms")
print(f"번역: {metrics.translation_latency_ms}ms")
print(f"역번역: {metrics.backtranslation_latency_ms}ms")
print(f"평가: {metrics.evaluation_latency_ms}ms")
print(f"토큰: {metrics.token_usage}")
```

### 구성요소 요약

| 구성요소 | 역할 |
|---------|------|
| `TranslationWorkflowConfig` | 설정 (재시도 횟수, 후보 수, 타임아웃) |
| `build_translation_graph()` | Strands GraphBuilder로 그래프 빌드 |
| `run()` | 단일 번역 실행 + 메트릭 수집 |
| `_calculate_metrics()` | 지연시간/토큰 집계 |

---

## 빠른 시작

### 단일 번역

```python
import asyncio
from src.graph.builder import TranslationWorkflowGraphV2, TranslationWorkflowConfig
from src.models import TranslationUnit

async def main():
    unit = TranslationUnit(
        key="IDS_FAQ_001",
        source_text="ABC 클라우드에서 동기화가 되지 않습니다.",
        target_lang="en-rUS",
        product="abc_cloud"
    )

    config = TranslationWorkflowConfig(max_regenerations=2)
    graph = TranslationWorkflowGraphV2(config)
    result = await graph.run(unit)

    print(f"상태: {result['workflow_state'].value}")
    if result['workflow_state'].value == 'published':
        print(f"번역: {result['final_translation']}")

asyncio.run(main())
```

---

## 설정 옵션

```python
from src.graph.builder import TranslationWorkflowConfig

config = TranslationWorkflowConfig(
    max_regenerations=1,          # 최대 재생성 횟수 (기본: 1)
    num_candidates=1,             # 번역 후보 수 (기본: 1)
    enable_backtranslation=True,  # 역번역 활성화 (기본: True)
    timeout_seconds=120,          # 타임아웃 (기본: 120초)
    max_node_executions=15        # 무한 루프 방지 (기본: 15)
)

graph = TranslationWorkflowGraphV2(config)
```

---

## 결과 구조

```python
result = await graph.run(unit)

# 주요 필드
result['workflow_state']      # WorkflowState (PUBLISHED, REJECTED, etc.)
result['final_translation']   # 최종 번역 (PASS인 경우)
result['attempt_count']       # 총 시도 횟수
result['gate_decision']       # GateDecision (점수, 판정, 메시지)
result['agent_results']       # List[AgentResult] (3개 평가 결과)
result['metrics']             # WorkflowMetrics (지연시간, 토큰 사용량)
```

---

## 상태 관리 (WorkflowStateManager)

GraphBuilder 노드 간 데이터 공유를 위해 **글로벌 상태 관리자**를 사용합니다.

### 왜 글로벌 상태인가?

Strands GraphBuilder의 노드는 `task` 파라미터만 받습니다. 기존 Dict 기반 상태 전달이 불가능하므로, 글로벌 상태 패턴으로 노드 간 데이터를 공유합니다.

```
기존 패턴 (LangGraph):           GraphBuilder 패턴:
┌─────────────────────┐         ┌─────────────────────┐
│ def node(state):    │         │ def node(task):     │
│   unit = state[".."]│    →    │   state = get_wf..()│
│   state["result"]=..│         │   unit = state[".."]│
│   return state      │         │   state["result"]=..│
└─────────────────────┘         └─────────────────────┘
```

### 초기 상태 (create_workflow)

```python
initial_state = {
    "workflow_id": "uuid-...",
    "unit": TranslationUnit(...),       # 번역 단위
    "attempt_count": 1,                  # 현재 시도 횟수
    "num_candidates": 1,                 # 번역 후보 수
    "max_regenerations": 1,              # 최대 재생성 횟수
    "workflow_state": WorkflowState.INITIALIZED,
    "created_at": datetime.now(),
    "token_usage": {                     # 토큰 추적
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "by_agent": {}
    }
}
```

### 사용 방법

#### 1. 컨텍스트 매니저 (권장)

```python
from src.utils.workflow_state import workflow_context, get_workflow_state

# 워크플로우 생성 → 실행 → 정리를 자동 처리
with workflow_context(unit, config) as workflow_id:
    result = await graph.invoke_async(task)
    final_state = get_workflow_state(workflow_id)

# with 블록 종료 시 자동 cleanup
```

#### 2. 노드 내에서 상태 접근

```python
async def translate_node(task=None, **kwargs):
    # 글로벌 상태에서 데이터 가져오기
    state = get_workflow_state()
    unit = state["unit"]
    feedback = state.get("feedback")  # 재생성 시 피드백

    # 번역 수행
    result = await translate(...)

    # 결과를 글로벌 상태에 저장
    state["translation_result"] = result
    state["workflow_state"] = WorkflowState.TRANSLATING

    return {"status": "completed"}  # GraphBuilder 반환값 (로깅용)
```

#### 3. 상태 업데이트 함수

```python
from src.utils.workflow_state import update_workflow_state

# 여러 필드 한번에 업데이트
update_workflow_state({
    "translation_result": result,
    "workflow_state": WorkflowState.TRANSLATING
})
```

### 주요 함수

| 함수 | 설명 |
|------|------|
| `workflow_context(unit, config)` | 컨텍스트 매니저 (생성→정리 자동) |
| `get_workflow_state(workflow_id?)` | 현재 상태 가져오기 (직접 수정 가능) |
| `update_workflow_state(updates)` | 상태 업데이트 |
| `get_state_manager()` | 싱글톤 관리자 인스턴스 |

### 스레드 안전성

`_states_lock`으로 동시 접근 보호:

```python
_workflow_states: Dict[str, Dict[str, Any]] = {}  # 워크플로우별 상태
_states_lock = threading.Lock()                    # 동시 접근 보호
_current_workflow_id: Optional[str] = None         # 현재 활성 ID
```

---

## 관련 모듈

| 모듈 | 역할 |
|------|------|
| `src/tools/` | 번역 및 평가 도구 |
| `src/models/` | 데이터 모델 |
| `src/utils/strands_utils.py` | FunctionNode, Agent 유틸리티 |
| `src/utils/workflow_state.py` | 글로벌 상태 관리 |
| `sops/` | 의사결정 로직 (EvaluationGateSOP, RegenerationSOP) |
| `src/prompts/` | 시스템 프롬프트 |
