# Graph - 워크플로우 오케스트레이션

번역 파이프라인을 State Machine 패턴으로 오케스트레이션하는 모듈입니다.

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
┌─────────────────────────────────────────────────────────────────────────────┐
│                              번역 파이프라인                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    [1] 번역        [2] 역번역       [3] 평가         [4] 판정        [5] 최종
   ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
   │translate│────▶│  back  │────▶│evaluate│────▶│ decide │────▶│finalize│
   │  _node │     │translate│     │ _node  │     │ _node  │     │ _node  │
   └────────┘     │ _node  │     └────────┘     └────────┘     └────────┘
       ▲          └────────┘          │              │              │
       │                              │              │              ▼
       │                         ┌────┴────┐   ┌────┴────┐    ┌─────────┐
       │                         │ 3 Agent │   │  REGEN  │    │ 발행    │
       │                         │ 병렬실행 │   │  ERATE  │    │ 거부    │
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
| `unit` | `TranslationUnit` | ✅ | 번역할 단위 |
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
| `unit` | `TranslationUnit` | ✅ | 언어 정보용 |

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
| `unit` | `TranslationUnit` | ✅ | 원문 및 용어집 |
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
| 점수 3-4, 재시도 소진 | `REJECTED` | 거부 (HITL 미구현) |
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

`TranslationWorkflowGraph`는 노드들을 오케스트레이션하는 **메인 컨트롤러**입니다.

### 클래스 구조

```python
class TranslationWorkflowGraph:
    def __init__(self, config: WorkflowConfig = None)
    async def run(self, unit: TranslationUnit) -> Dict[str, Any]
    async def run_batch(self, units: list, concurrency: int = 5) -> list
```

### `run()` 메서드 실행 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                        run(unit)                                 │
├─────────────────────────────────────────────────────────────────┤
│  1. 초기 상태 생성                                               │
│     state = {unit, attempt_count=1, workflow_state=INITIALIZED} │
│                                                                  │
│  2. _run_pipeline(state) 호출                                    │
│                          ↓                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  while True 루프                         │    │
│  │  ┌──────────────┐                                       │    │
│  │  │ translate    │ → state["translation_result"]         │    │
│  │  └──────────────┘                                       │    │
│  │          ↓                                              │    │
│  │  ┌──────────────┐                                       │    │
│  │  │ backtranslate│ → state["backtranslation_result"]     │    │
│  │  └──────────────┘                                       │    │
│  │          ↓                                              │    │
│  │  ┌──────────────┐                                       │    │
│  │  │ evaluate     │ → state["agent_results"] (3개 병렬)    │    │
│  │  └──────────────┘                                       │    │
│  │          ↓                                              │    │
│  │  ┌──────────────┐                                       │    │
│  │  │ decide       │ → state["gate_decision"]              │    │
│  │  └──────────────┘                                       │    │
│  │          ↓                                              │    │
│  │  ┌──────────────────────────────────────────────────┐   │    │
│  │  │              라우팅 로직                          │   │    │
│  │  │  if should_finalize():  → finalize → break       │   │    │
│  │  │  if should_regenerate(): → regenerate → continue │   │    │
│  │  └──────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  3. 메트릭 계산 → state["metrics"]                               │
│                                                                  │
│  4. return state                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 라우팅 헬퍼 함수

```python
def should_regenerate(state) -> bool:
    """verdict가 REGENERATE인지 확인"""
    return state["gate_decision"].verdict == Verdict.REGENERATE

def should_finalize(state) -> bool:
    """verdict가 PASS, BLOCK, ESCALATE 중 하나인지 확인"""
    return verdict in [Verdict.PASS, Verdict.BLOCK, Verdict.ESCALATE]

def is_failed(state) -> bool:
    """워크플로우가 실패 상태인지 확인"""
    return state["workflow_state"] == WorkflowState.FAILED
```

### `_run_pipeline()` 핵심 로직

```python
async def _run_pipeline(self, state):
    while True:
        # Step 1-4: 순차 실행
        state = await translate_node(state)
        state = await backtranslate_node(state)
        state = await evaluate_node(state)
        state = await decide_node(state)

        # Step 5: 라우팅
        if should_finalize(state):
            state = await finalize_node(state)
            break  # 루프 종료

        if should_regenerate(state):
            if attempt_count > max_regenerations:
                break  # 최대 재시도 초과
            state = await regenerate_node(state)
            continue  # 루프 반복 (translate부터 다시)

    return state
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

### 배치 처리 (`run_batch`)

```python
async def run_batch(self, units: list, concurrency: int = 5):
    semaphore = Semaphore(concurrency)  # 동시 실행 제한

    async def run_with_semaphore(unit):
        async with semaphore:
            return await self.run(unit)

    results = await asyncio.gather(
        *[run_with_semaphore(unit) for unit in units]
    )
    return results
```

**동시성 제어:**
| 설정 | 동작 |
|------|------|
| `concurrency=5` | 최대 5개 번역이 동시 실행 |
| 각 번역 내 | 3개 평가 에이전트 병렬 실행 |
| 최대 호출 | 15개 에이전트 동시 호출 가능 |

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
| `WorkflowConfig` | 설정 (재시도 횟수, 후보 수, 타임아웃) |
| `run()` | 단일 번역 실행 + 메트릭 수집 |
| `_run_pipeline()` | while 루프로 노드 실행 + 라우팅 |
| `run_batch()` | Semaphore로 동시성 제어 배치 처리 |
| `_calculate_metrics()` | 지연시간/토큰 집계 |

---

## 빠른 시작

### 단일 번역

```python
import asyncio
from src.graph import TranslationWorkflowGraph
from src.models import TranslationUnit

async def main():
    unit = TranslationUnit(
        key="IDS_FAQ_SC_ABOUT",
        source_text="ABC 클라우드는 데이터를 동기화합니다.",
        target_lang="en-rUS",
        glossary={"ABC 클라우드": "ABC Cloud"}
    )

    graph = TranslationWorkflowGraph()
    result = await graph.run(unit)

    print(f"상태: {result['workflow_state'].value}")
    if result['workflow_state'].value == 'published':
        print(f"번역: {result['final_translation']}")

asyncio.run(main())
```

### 배치 처리

```python
units = [unit1, unit2, unit3, ...]
results = await graph.run_batch(units, concurrency=10)
```

---

## 설정 옵션

```python
from src.graph import WorkflowConfig

config = WorkflowConfig(
    max_regenerations=1,          # 최대 재생성 횟수 (기본: 1)
    num_candidates=1,             # 번역 후보 수 (기본: 1)
    enable_backtranslation=True,  # 역번역 활성화 (기본: True)
    timeout_seconds=120           # 타임아웃 (기본: 120초)
)

graph = TranslationWorkflowGraph(config)
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

## 관련 모듈

| 모듈 | 역할 |
|------|------|
| `src/tools/` | 번역 및 평가 도구 |
| `src/models/` | 데이터 모델 |
| `sops/` | 의사결정 로직 (EvaluationGateSOP, RegenerationSOP) |
| `src/prompts/` | 시스템 프롬프트 |
