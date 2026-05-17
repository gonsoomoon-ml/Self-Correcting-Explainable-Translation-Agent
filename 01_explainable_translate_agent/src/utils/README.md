# 유틸리티 (Utils)

번역 에이전트에서 공통으로 사용하는 유틸리티 모듈입니다.

> **참고**: 이 모듈은 `/home/ubuntu/sample-deep-insight/self-hosted`의 프로덕션 검증된 패턴을 기반으로 구현되었습니다.

## 개요

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Strands Agent 기반 구조                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  strands_utils.py (권장)              config.py                      │
│  ┌──────────────────────┐            ┌──────────────────────┐       │
│  │ get_agent()          │            │ get_config()         │       │
│  │ get_model()          │            │ get_thresholds()     │       │
│  │ run_agent_async()    │            │ get_risk_profile()   │       │
│  │ TokenTracker         │            └──────────────────────┘       │
│  └──────────┬───────────┘                                           │
│             │                                                        │
│             ▼                                                        │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ BedrockModel (Strands SDK)                                │       │
│  │ ├─ Prompt Caching     → 시스템 프롬프트 90% 비용 절감      │       │
│  │ ├─ Auto Retry         → 쓰로틀링 자동 재시도 (지수 백오프) │       │
│  │ ├─ Thinking Mode      → 확장된 추론 모드 지원             │       │
│  │ └─ Token Tracking     → 에이전트별 토큰 사용량 추적       │       │
│  └──────────────────────────────────────────────────────────┘       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 파일 구조

```
src/utils/
├── __init__.py          # 모듈 익스포트
├── strands_utils.py     # Strands Agent 유틸리티 (권장) ⭐
├── observability.py     # 로깅, 트레이싱, 메트릭 수집 ⭐
├── config.py            # 설정 파일 로더
└── bedrock_client.py    # ⚠️ DEPRECATED (raw boto3 - 사용 금지)
```

---

## strands_utils.py (Strands Agent 유틸리티)

Strands Agent SDK를 사용한 LLM 통합 모듈입니다.

### 주요 기능

| 기능 | 설명 | 비용 영향 |
|------|------|----------|
| **프롬프트 캐싱** | 시스템 프롬프트를 캐싱하여 재사용 | 90% 비용 절감 |
| **쓰로틀링 재시도** | API 제한 시 지수 백오프로 자동 재시도 | 안정성 향상 |
| **토큰 추적** | 에이전트별/모델별 사용량 추적 | 비용 가시성 |
| **상태 관리** | 에이전트 간 상태 공유 | 워크플로우 지원 |

### 기본 사용법

```python
from src.utils import get_agent, run_agent_async

# 에이전트 생성 (프롬프트 캐싱 자동 활성화)
agent = get_agent(
    role="translator",
    system_prompt="당신은 전문 번역가입니다. 한국어를 영어로 번역하세요."
)

# 동기 실행
result = agent("안녕하세요, ABC 클라우드입니다.")
print(result.message["content"][-1]["text"])

# 비동기 실행 (권장 - 쓰로틀링 재시도 포함)
result = await run_agent_async(agent, "안녕하세요, ABC 클라우드입니다.")
print(result["text"])
print(result["usage"])  # 토큰 사용량
```

---

## 프롬프트 캐싱 (Prompt Caching)

### 작동 원리

```
┌─────────────────────────────────────────────────────────────────┐
│                    프롬프트 캐싱 흐름                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  첫 번째 호출                      두 번째 호출 이후              │
│  ┌─────────────────┐              ┌─────────────────┐           │
│  │ System Prompt   │              │ System Prompt   │           │
│  │ (2000 tokens)   │              │ (캐시에서 로드)  │           │
│  └────────┬────────┘              └────────┬────────┘           │
│           │                                │                     │
│           ▼                                ▼                     │
│  cache_write: 2000 tokens         cache_read: 2000 tokens       │
│  비용: 125% (25% 추가)             비용: 10% (90% 할인!)         │
│                                                                  │
│  ────────────────────────────────────────────────────────────   │
│  💡 10회 호출 시 비용 비교:                                       │
│     캐싱 없음: 2000 × 10 = 20,000 토큰 (100%)                    │
│     캐싱 사용: 2000×1.25 + 2000×0.1×9 = 4,300 토큰 (21.5%)       │
│     → 약 78% 비용 절감!                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 캐싱 활성화

```python
from src.utils import get_agent

# 프롬프트 캐싱 활성화 (기본값: True)
agent = get_agent(
    role="translator",
    system_prompt="...",  # 이 프롬프트가 캐싱됨
    prompt_cache=True,    # 기본값
    cache_type="default"  # "default"(영구) 또는 "ephemeral"(5분)
)

# 첫 호출: 캐시 생성 (cache_write_input_tokens)
result1 = await run_agent_async(agent, "번역해주세요: 안녕하세요")
# → cache_write_input_tokens = 500 (25% 추가 비용)

# 두 번째 호출: 캐시 히트 (cache_read_input_tokens)
result2 = await run_agent_async(agent, "번역해주세요: 감사합니다")
# → cache_read_input_tokens = 500 (90% 할인!)
```

### 캐시 타입

| 타입 | 설명 | 사용 사례 |
|------|------|----------|
| `default` | 영구 캐시 (세션 유지) | 배치 번역, 반복 작업 |
| `ephemeral` | 5분 후 만료 | 일회성 작업, 테스트 |

---

## 역할별 에이전트 생성

### 역할별 모델 매핑

| 역할 | 모델 | 용도 | 특징 |
|------|------|------|------|
| `translator` | **Opus 4.5** | 메인 번역 | 고품질, 뉘앙스 파악 |
| `backtranslator` | Sonnet 4.5 | 역번역 검증 | 빠른 속도 |
| `accuracy_evaluator` | Sonnet 4.5 | 정확성 평가 | 의미 검증 |
| `compliance_evaluator` | Sonnet 4.5 | 컴플라이언스 평가 | 용어집/규칙 검증 |
| `quality_evaluator` | **Opus 4.5** | 품질 평가 | 자연스러움 평가 |

### 에이전트 생성 예시

```python
from src.utils import get_agent

# Translator (Opus 4.5 - 고품질 번역)
translator = get_agent(
    role="translator",
    system_prompt="""당신은 ABC 클라우드 전문 번역가입니다.
    한국어를 미국 영어로 번역하세요.
    용어집의 용어를 반드시 사용하세요."""
)

# Backtranslator (Sonnet 4.5 - 빠른 역번역)
backtranslator = get_agent(
    role="backtranslator",
    system_prompt="영어를 한국어로 역번역하세요."
)

# Accuracy Evaluator (Sonnet 4.5 - 정확성 검증)
accuracy_evaluator = get_agent(
    role="accuracy_evaluator",
    system_prompt="""원문과 번역문의 의미 정확성을 평가하세요.
    0-5점으로 점수를 매기세요."""
)
```

### get_agent() 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `role` | str | 필수 | 역할 (translator, backtranslator 등) |
| `system_prompt` | str | 필수 | 시스템 프롬프트 |
| `agent_name` | str | role | 로깅용 에이전트 이름 |
| `prompt_cache` | bool | True | 프롬프트 캐싱 활성화 |
| `cache_type` | str | "default" | 캐시 타입 |
| `tools` | List | None | 에이전트 도구 목록 |
| `streaming` | bool | True | 스트리밍 활성화 |
| `tool_cache` | bool | False | 도구 캐싱 활성화 |
| `enable_reasoning` | bool | False | 확장 추론 모드 (Thinking) |

---

## 쓰로틀링 재시도 (Throttling Retry)

AWS Bedrock API 제한 시 자동으로 재시도합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    쓰로틀링 재시도 흐름                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  요청 ──▶ ThrottlingException 발생                              │
│              │                                                   │
│              ▼                                                   │
│         ┌─────────────────────────────────────────┐             │
│         │ 지수 백오프 (Exponential Backoff)        │             │
│         │                                          │             │
│         │  시도 1: 10초 대기                       │             │
│         │  시도 2: 20초 대기                       │             │
│         │  시도 3: 40초 대기                       │             │
│         │  시도 4: 80초 대기                       │             │
│         │  시도 5: 최종 실패 시 예외 발생          │             │
│         └─────────────────────────────────────────┘             │
│                                                                  │
│  💡 run_agent_async()는 자동으로 재시도 로직 포함                 │
└─────────────────────────────────────────────────────────────────┘
```

```python
# 비동기 실행 (재시도 자동 포함)
result = await run_agent_async(agent, message, use_retry=True)  # 기본값

# 재시도 없이 실행 (테스트용)
result = await run_agent_async(agent, message, use_retry=False)
```

---

## TokenTracker (토큰 사용량 추적)

번역 파이프라인 전체에서 토큰 사용량을 추적하고 비용을 분석합니다.

### 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                    TokenTracker 워크플로우                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │Translator│───▶│Backtrans │───▶│Evaluator │───▶│Evaluator │  │
│  │ (Opus)   │    │ (Sonnet) │    │ (Sonnet) │    │ (Opus)   │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    TokenTracker                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │ shared_state['token_usage']                         │ │   │
│  │  │ ├─ total_input_tokens: 15,000                       │ │   │
│  │  │ ├─ cache_read_input_tokens: 8,000 (90% 할인)        │ │   │
│  │  │ ├─ cache_write_input_tokens: 2,000 (25% 추가)       │ │   │
│  │  │ ├─ total_output_tokens: 3,000                       │ │   │
│  │  │ └─ by_agent: {translator: {...}, ...}               │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 기본 사용법

```python
from src.utils import get_agent, TokenTracker

# 1. 공유 상태 초기화
shared_state = {}
TokenTracker.initialize(shared_state)

# 2. 각 에이전트 실행 후 사용량 누적
translator = get_agent(role="translator", system_prompt="...")
result = translator("Translate: 안녕하세요")
TokenTracker.accumulate_from_agent(translator, "translator", shared_state)

backtranslator = get_agent(role="backtranslator", system_prompt="...")
result = backtranslator("Translate back: Hello")
TokenTracker.accumulate_from_agent(backtranslator, "backtranslator", shared_state)

# 3. 현재 누적 사용량 확인 (간략)
TokenTracker.print_current(shared_state)

# 4. 상세 요약 출력
TokenTracker.print_summary(shared_state)
```

### 번역 파이프라인 예시

```python
from src.utils import get_agent, TokenTracker, run_agent_async

async def translate_with_tracking(source_text: str) -> dict:
    """토큰 추적이 포함된 번역 파이프라인"""

    # 공유 상태 초기화
    shared_state = {}
    TokenTracker.initialize(shared_state)

    # 1. 번역
    translator = get_agent(role="translator", system_prompt="...")
    translation = await run_agent_async(translator, source_text)
    TokenTracker.accumulate_from_agent(translator, "translator", shared_state)

    # 2. 역번역
    backtranslator = get_agent(role="backtranslator", system_prompt="...")
    backtrans = await run_agent_async(backtranslator, translation["text"])
    TokenTracker.accumulate_from_agent(backtranslator, "backtranslator", shared_state)

    # 3. 평가 (병렬 실행 가능)
    for evaluator_role in ["accuracy_evaluator", "compliance_evaluator", "quality_evaluator"]:
        evaluator = get_agent(role=evaluator_role, system_prompt="...")
        result = await run_agent_async(evaluator, f"Evaluate: {translation['text']}")
        TokenTracker.accumulate_from_agent(evaluator, evaluator_role, shared_state)

    # 4. 결과 반환
    return {
        "translation": translation["text"],
        "token_usage": TokenTracker.to_dict(shared_state),
        "cache_hit_ratio": TokenTracker.get_cache_savings_ratio(shared_state)
    }
```

### TokenTracker 출력 예시

```
============================================================
=== Token Usage Summary ===
============================================================

Total Tokens: 15,000
Model(s) Used: claude-opus-4-5, claude-sonnet-4-5
  - Regular Input:     5,000 (100% cost)
  - Cache Read:        8,000 (10% cost - 90% discount)
  - Cache Write:       1,000 (125% cost - 25% extra)
  - Output:            1,000

  Cache Hit Ratio: 88.9%

------------------------------------------------------------
Model Usage Summary (for cost calculation):
------------------------------------------------------------

  [claude-opus-4-5]
    Total: 8,000
    - Regular Input:     2,000 (100% cost)
    - Cache Read:        4,000 (10% cost - 90% discount)
    - Cache Write:         500 (125% cost - 25% extra)
    - Output:            1,500
    Used by: translator, quality_evaluator

  [claude-sonnet-4-5]
    Total: 7,000
    - Regular Input:     3,000 (100% cost)
    - Cache Read:        4,000 (10% cost - 90% discount)
    - Cache Write:         500 (125% cost - 25% extra)
    - Output:              500
    Used by: backtranslator, accuracy_evaluator, compliance_evaluator

------------------------------------------------------------
Token Usage by Agent:
------------------------------------------------------------

  [translator] Total: 3,500
    Model: claude-opus-4-5
    - Regular Input:     1,000 (100% cost)
    - Cache Read:        2,000 (10% cost - 90% discount)
    - Cache Write:         200 (125% cost - 25% extra)
    - Output:              300

  [accuracy_evaluator] Total: 2,500
    Model: claude-sonnet-4-5
    ...
============================================================
```

### TokenTracker 메서드

| 메서드 | 설명 |
|--------|------|
| `initialize(state)` | 토큰 추적 구조 초기화 |
| `accumulate_from_agent(agent, name, state)` | 에이전트 사용량 누적 (편의 메서드) |
| `accumulate(event, state)` | 이벤트 딕셔너리로 사용량 누적 |
| `get_usage(state)` | 현재 사용량 딕셔너리 반환 |
| `get_total_tokens(state)` | 총 토큰 수 반환 |
| `get_cache_savings_ratio(state)` | 캐시 히트 비율 반환 (0-1) |
| `print_current(state)` | 현재 누적 사용량 출력 (간략) |
| `print_summary(state)` | 상세 사용량 요약 출력 |
| `to_dict(state)` | JSON 직렬화용 딕셔너리 변환 |

### TranslationRecord에 저장

```python
from src.models import TranslationRecord
from src.utils import TokenTracker

# 번역 완료 후
record = TranslationRecord(unit=unit, ...)

# 토큰 사용량을 메타데이터에 저장
record.metadata["token_usage"] = TokenTracker.to_dict(shared_state)

# 저장된 데이터 예시:
# {
#     "total_input_tokens": 5000,
#     "total_output_tokens": 1000,
#     "total_tokens": 6000,
#     "cache_read_input_tokens": 4000,
#     "cache_write_input_tokens": 500,
#     "cache_hit_ratio": 0.889,
#     "by_agent": {
#         "translator": {"input": 1000, "output": 300, ...},
#         ...
#     }
# }
```

---

## 상태 관리 (State Management)

에이전트 간 상태를 공유합니다.

```python
from src.utils import get_agent, get_agent_state, update_agent_state

agent = get_agent(role="translator", system_prompt="...")

# 상태 설정
update_agent_state(agent, "current_language", "en-rUS")
update_agent_state(agent, "glossary_loaded", True)

# 상태 조회
lang = get_agent_state(agent, "current_language")  # "en-rUS"
missing = get_agent_state(agent, "missing_key", default_value="default")  # "default"

# 전체 상태 조회
all_state = get_agent_state_all(agent)  # {"current_language": "en-rUS", ...}
```

---

## observability.py (Observability)

OpenTelemetry 기반의 분산 추적 및 observability 모듈입니다.

> **참고**: Bedrock AgentCore의 패턴을 기반으로 구현되었습니다.
> `/home/ubuntu/sample-deep-insight/managed-agentcore/src/utils/agentcore_observability.py`

### 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                OpenTelemetry 기반 Observability                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Session Context (Baggage)        Tracer                        │
│  ┌──────────────────────┐        ┌──────────────────────┐       │
│  │ session.id           │        │ get_tracer()         │       │
│  │ user.type            │        │ trace_workflow()     │       │
│  │ workflow.type        │◀──────▶│ trace_agent()        │       │
│  │ target.lang          │        └──────────────────────┘       │
│  └──────────────────────┘                  │                    │
│             │                              ▼                    │
│             ▼                    ┌──────────────────────┐       │
│  서비스 간 컨텍스트 전파            │ Span Helpers          │       │
│  (Cross-service propagation)     │ ├─ add_span_event()   │       │
│                                  │ ├─ set_span_attribute│       │
│                                  │ ├─ set_span_status() │       │
│                                  │ └─ record_exception()│       │
│                                  └──────────────────────┘       │
│                                            │                    │
│                                            ▼                    │
│                                  ┌──────────────────────┐       │
│                                  │ AWS X-Ray 연동        │       │
│                                  │ (분산 추적 시각화)     │       │
│                                  └──────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Session Context (Baggage)

세션 컨텍스트를 OpenTelemetry Baggage로 설정하여 서비스 간 전파합니다.

```python
from src.utils import set_session_context, get_session_id
from opentelemetry import context

# 세션 컨텍스트 설정
token = set_session_context(
    session_id="abc-123",
    user_type="batch",
    workflow_type="translation",
    target_lang="en-rUS"
)

# 현재 세션 ID 조회
session_id = get_session_id()  # "abc-123"

# 작업 완료 후 컨텍스트 정리
context.detach(token)
```

### Tracer (OpenTelemetry Tracer)

OpenTelemetry Tracer를 사용하여 Span을 생성합니다.

```python
from src.utils import get_tracer, add_span_event, set_span_attribute

# Tracer 가져오기
tracer = get_tracer()

# Span 생성
with tracer.start_as_current_span("translate") as span:
    # 속성 설정
    set_span_attribute(span, "source_lang", "ko")
    set_span_attribute(span, "target_lang", "en-rUS")
    set_span_attribute(span, "input_length", len(source_text))

    # 이벤트 기록
    add_span_event(span, "input_message", {"text": source_text[:100]})

    # 작업 수행
    result = translate(source_text)

    # 결과 이벤트
    add_span_event(span, "response", {
        "text": result[:100],
        "length": len(result)
    })
```

### trace_workflow() (워크플로우 추적)

전체 워크플로우를 추적하는 컨텍스트 매니저입니다.

```python
from src.utils import trace_workflow, trace_agent, set_span_attribute

# 워크플로우 시작 (자동으로 세션 컨텍스트 설정)
with trace_workflow("translation_pipeline") as (span, session_id):
    set_span_attribute(span, "source_lang", "ko")
    set_span_attribute(span, "target_lang", "en-rUS")

    # 에이전트 실행
    with trace_agent("translator") as (agent_span, record):
        record("input", {"text": source_text})
        result = translator(source_text)
        record("output", {"text": result, "score": 4})

    with trace_agent("accuracy_evaluator") as (agent_span, record):
        record("input", {"original": source_text, "translation": result})
        score = evaluator(source_text, result)
        record("output", {"score": score})
```

### trace_agent() (에이전트 추적)

개별 에이전트 실행을 추적합니다.

```python
from src.utils import trace_agent

with trace_agent("translator") as (span, record):
    # 입력 기록
    record("input", {
        "source_text": source_text,
        "target_lang": "en-rUS"
    })

    # 에이전트 실행
    result = await run_agent_async(translator, source_text)

    # 출력 기록
    record("output", {
        "translation": result["text"],
        "tokens": result["usage"]["output_tokens"]
    })

    # 성공 시 자동으로 status = OK
    # 예외 발생 시 자동으로 status = ERROR
```

### Span Helpers

Span에 속성, 이벤트, 상태를 설정하는 헬퍼 함수들입니다.

```python
from src.utils import (
    add_span_event,
    set_span_attribute,
    set_span_status,
    record_exception
)

with tracer.start_as_current_span("evaluate") as span:
    try:
        # 속성 설정
        set_span_attribute(span, "evaluator", "accuracy")
        set_span_attribute(span, "threshold", 3)

        # 이벤트 기록 (타임스탬프 자동)
        add_span_event(span, "evaluation_started", {"model": "sonnet"})

        score = evaluate(translation)

        add_span_event(span, "evaluation_completed", {"score": score})

        # 성공 상태 설정
        set_span_status(span, success=True)

    except Exception as e:
        # 예외 기록
        record_exception(span, e)
        raise
```

### Node Logging

노드 실행 시작/완료를 로깅합니다.

```python
from src.utils import log_node_start, log_node_complete, TokenTracker

# 노드 시작 로깅
log_node_start("Translator")
# 출력: ===== Translator started =====

# 에이전트 실행
result = await run_agent_async(translator, source_text)
TokenTracker.accumulate_from_agent(translator, "translator", shared_state)

# 노드 완료 로깅 (토큰 사용량 포함)
log_node_complete("Translator", shared_state)
# 출력: ===== Translator completed =====
#       Current token usage: input=1200, output=350, cache_read=800
```

### 비용 계산

모델별 토큰 비용을 계산합니다.

```python
from src.utils import calculate_cost, MODEL_PRICING

# 비용 계산
cost = calculate_cost(
    model_id="claude-opus-4-5",
    input_tokens=500,
    output_tokens=200,
    cache_read_tokens=400,
    cache_write_tokens=100
)
print(f"Estimated cost: ${cost:.6f}")

# 가격표 (1M 토큰당 USD)
# MODEL_PRICING = {
#     "claude-opus-4-5": {
#         "input": 15.0,       # $15 per 1M input
#         "output": 75.0,      # $75 per 1M output
#         "cache_read": 1.5,   # 90% 할인
#         "cache_write": 18.75 # 25% 추가
#     },
#     "claude-sonnet-4-5": {
#         "input": 3.0,
#         "output": 15.0,
#         "cache_read": 0.3,
#         "cache_write": 3.75
#     }
# }
```

### AWS X-Ray 연동

OpenTelemetry SDK와 OTLP Exporter를 설정하면 AWS X-Ray로 자동 전송됩니다.

```python
# 환경 변수 설정 (런타임 전)
import os
os.environ["TRACER_MODULE_NAME"] = "translation_agent"
os.environ["TRACER_LIBRARY_VERSION"] = "1.0.0"

# OTLP Exporter 설정 (main.py에서)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Provider 설정
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
```

### 번역 파이프라인 통합 예시

```python
from src.utils import (
    trace_workflow, trace_agent,
    set_span_attribute, add_span_event,
    log_node_start, log_node_complete,
    TokenTracker, calculate_cost
)

async def translate_with_observability(source_text: str) -> dict:
    """Observability가 포함된 번역 파이프라인"""

    # 공유 상태 초기화
    shared_state = {}
    TokenTracker.initialize(shared_state)

    # 워크플로우 시작
    with trace_workflow("translation_pipeline") as (workflow_span, session_id):
        set_span_attribute(workflow_span, "source_lang", "ko")
        set_span_attribute(workflow_span, "target_lang", "en-rUS")

        # 1. 번역
        log_node_start("Translator")
        with trace_agent("translator") as (span, record):
            record("input", {"text": source_text})
            result = await run_agent_async(translator, source_text)
            TokenTracker.accumulate_from_agent(translator, "translator", shared_state)
            record("output", {"text": result["text"]})
        log_node_complete("Translator", shared_state)

        # 2. 평가
        log_node_start("Evaluators")
        for evaluator_role in ["accuracy", "compliance", "quality"]:
            with trace_agent(f"{evaluator_role}_evaluator") as (span, record):
                record("input", {"translation": result["text"]})
                score = await run_agent_async(evaluators[evaluator_role], result["text"])
                TokenTracker.accumulate_from_agent(
                    evaluators[evaluator_role],
                    f"{evaluator_role}_evaluator",
                    shared_state
                )
                record("output", {"score": score})
        log_node_complete("Evaluators", shared_state)

        # 3. 결과 속성 설정
        usage = TokenTracker.to_dict(shared_state)
        set_span_attribute(workflow_span, "total_tokens", usage["total_tokens"])
        set_span_attribute(workflow_span, "cache_hit_ratio", usage["cache_hit_ratio"])

        # 비용 계산
        cost = calculate_cost(
            model_id="claude-opus-4-5",
            input_tokens=usage["total_input_tokens"],
            output_tokens=usage["total_output_tokens"],
            cache_read_tokens=usage.get("cache_read_input_tokens", 0)
        )
        set_span_attribute(workflow_span, "estimated_cost_usd", cost)

    return {
        "translation": result["text"],
        "session_id": session_id,
        "token_usage": usage,
        "estimated_cost": cost
    }
```

### Observability 함수 요약

| 함수 | 설명 |
|------|------|
| `get_tracer()` | OpenTelemetry Tracer 가져오기 |
| `set_session_context(session_id, ...)` | Baggage로 세션 컨텍스트 설정 |
| `get_session_id()` | 현재 세션 ID 조회 |
| `trace_workflow(name)` | 워크플로우 추적 컨텍스트 매니저 |
| `trace_agent(name)` | 에이전트 추적 컨텍스트 매니저 |
| `add_span_event(span, name, attrs)` | Span에 이벤트 추가 |
| `set_span_attribute(span, key, value)` | Span 속성 설정 |
| `set_span_status(span, success, msg)` | Span 상태 설정 |
| `record_exception(span, exception)` | Span에 예외 기록 |
| `log_node_start(name)` | 노드 시작 로깅 |
| `log_node_complete(name, state)` | 노드 완료 로깅 (토큰 포함) |
| `calculate_cost(model_id, ...)` | 토큰 비용 계산 |

---

## config.py (설정 로더)

YAML 설정 파일을 로드하는 유틸리티입니다.

```python
from src.utils import get_config, get_thresholds, get_risk_profile, ConfigLoader

# 편의 함수 사용
languages = get_config("languages")
thresholds = get_thresholds()
us_profile = get_risk_profile("abc_cloud", "US")

# ConfigLoader 인스턴스 사용
config = ConfigLoader()

# 언어 목록 조회
languages = config.get_languages()  # 41개 언어 리스트
source = config.get_source_language()  # {"code": "ko", "name": "Korean", ...}

# 모델 설정 조회
translator_config = config.get_model_config("translator")
print(translator_config["model_id"])

# 리스크 프로파일 목록 (제품별)
profiles = config.list_risk_profiles("abc_cloud")  # ["DEFAULT", "US"]
```

**캐싱:**
- 설정 파일은 `@lru_cache`로 캐싱됨
- 캐시 클리어: `config.clear_cache()`

---

## ⚠️ bedrock_client.py (DEPRECATED)

> **경고**: 이 모듈은 raw boto3 Converse API를 사용합니다.
> 프롬프트 캐싱 및 Strands Agent 기능을 위해 `strands_utils.py`를 사용하세요.

```python
# ❌ 비권장 (DEPRECATED)
from src.utils import get_bedrock_client
client = get_bedrock_client()
response = client.converse(role="translator", messages=[...])

# ✅ 권장
from src.utils import get_agent
agent = get_agent(role="translator", system_prompt="...")
result = agent("Translate: 안녕하세요")
```

---

## 에러 처리

### Strands Agent 에러

```python
from src.utils import get_agent

try:
    agent = get_agent(role="translator", system_prompt="...")
    result = agent("Translate: 안녕하세요")
except Exception as e:
    print(f"Agent 실행 실패: {e}")
```

### Config 에러

```python
from src.utils import get_config

try:
    config = get_config("nonexistent")
except FileNotFoundError as e:
    print(f"설정 파일 없음: {e}")
```

---

## 주요 함수 요약

### 에이전트 생성 및 실행

| 함수 | 설명 |
|------|------|
| `get_agent(role, system_prompt, ...)` | Strands Agent 생성 (프롬프트 캐싱 포함) |
| `get_model(role)` | BedrockModel 인스턴스 생성 |
| `run_agent_async(agent, message)` | 비동기 에이전트 실행 (재시도 포함) |
| `run_agent_sync(agent, message)` | 동기 에이전트 실행 |
| `parse_response_text(response)` | 응답에서 텍스트 추출 (추론 포함) |

### 토큰 및 상태 관리

| 함수 | 설명 |
|------|------|
| `extract_usage_from_agent(agent)` | 단일 에이전트 토큰 사용량 추출 |
| `TokenTracker.initialize(state)` | 토큰 추적 초기화 |
| `TokenTracker.accumulate_from_agent(agent, name, state)` | 에이전트 사용량 누적 |
| `TokenTracker.print_summary(state)` | 상세 사용량 출력 |
| `TokenTracker.to_dict(state)` | JSON 직렬화용 딕셔너리 변환 |
| `get_agent_state(agent, key)` | 에이전트 상태 조회 |
| `update_agent_state(agent, key, value)` | 에이전트 상태 업데이트 |

### Observability (OpenTelemetry)

| 함수 | 설명 |
|------|------|
| `get_tracer()` | OpenTelemetry Tracer 가져오기 |
| `set_session_context(session_id, ...)` | Baggage로 세션 컨텍스트 설정 |
| `get_session_id()` | 현재 세션 ID 조회 |
| `trace_workflow(name)` | 워크플로우 추적 컨텍스트 매니저 |
| `trace_agent(name)` | 에이전트 추적 컨텍스트 매니저 |
| `add_span_event(span, name, attrs)` | Span에 이벤트 추가 |
| `set_span_attribute(span, key, value)` | Span 속성 설정 |
| `set_span_status(span, success, msg)` | Span 상태 설정 |
| `record_exception(span, exception)` | Span에 예외 기록 |
| `log_node_start(name)` | 노드 시작 로깅 |
| `log_node_complete(name, state)` | 노드 완료 로깅 (토큰 포함) |
| `calculate_cost(model_id, ...)` | 토큰 비용 계산 |

### 설정 로드

| 함수 | 설명 |
|------|------|
| `get_config(name)` | YAML 설정 로드 |
| `get_thresholds()` | 평가 임계값 로드 |
| `get_risk_profile(product, country_code)` | 제품·국가 리스크 프로파일 로드 (strict) |
| `create_system_prompt_with_cache(prompt)` | 캐시 포인트가 포함된 시스템 프롬프트 생성 |
