"""
Observability - 번역 파이프라인을 위한 OpenTelemetry 기반 트레이싱

Bedrock AgentCore observability 패턴 기반 (sample-deep-insight/managed-agentcore 참조).

분산 트레이싱을 위한 AWS X-Ray 연동:
- 스팬 생성을 위한 OpenTelemetry tracer
- 세션 컨텍스트 전파를 위한 Baggage
- 입출력 로깅을 위한 스팬 이벤트
- 토큰 추적 통합

필수 패키지:
- opentelemetry-api
- opentelemetry-sdk
- opentelemetry-exporter-otlp (AWS X-Ray용)
"""

import os
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager

# OpenTelemetry imports
from opentelemetry import baggage, context, trace
from opentelemetry.trace import Status, StatusCode

# 로거 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# =============================================================================
# 상수
# =============================================================================

# 기본 tracer 설정
DEFAULT_TRACER_MODULE_NAME = "translation_agent"
DEFAULT_TRACER_VERSION = "1.0.0"

# 터미널 출력용 ANSI 색상 코드
class Colors:
    """터미널 출력용 ANSI 색상 코드"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RED = '\033[91m'
    END = '\033[0m'


# 1M 토큰당 가격 (비용 추정용)
MODEL_PRICING = {
    "claude-opus-4-5": {
        "input": 15.0,      # 1M 입력 토큰당 $15
        "output": 75.0,     # 1M 출력 토큰당 $75
        "cache_read": 1.5,  # 90% 할인
        "cache_write": 18.75,  # 25% 추가
    },
    "claude-sonnet-4-5": {
        "input": 3.0,       # 1M 입력 토큰당 $3
        "output": 15.0,     # 1M 출력 토큰당 $15
        "cache_read": 0.3,  # 90% 할인
        "cache_write": 3.75,  # 25% 추가
    },
    "default": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.3,
        "cache_write": 3.75,
    }
}


# =============================================================================
# 세션 컨텍스트 (Baggage)
# =============================================================================

def set_session_context(
    session_id: str,
    user_type: Optional[str] = None,
    workflow_type: Optional[str] = None,
    target_lang: Optional[str] = None
) -> Any:
    """
    OpenTelemetry baggage를 사용하여 세션 컨텍스트를 설정합니다.

    Baggage는 서비스 경계를 넘어 컨텍스트를 전파하여
    모든 하위 스팬에서 사용할 수 있게 합니다.

    Args:
        session_id: 고유 세션/요청 ID
        user_type: 사용자 유형 (예: "batch", "interactive")
        workflow_type: 워크플로우 유형 (예: "translation", "evaluation")
        target_lang: 대상 언어 코드 (예: "en-rUS")

    Returns:
        나중에 detach할 컨텍스트 토큰

    Example:
        token = set_session_context(
            session_id="abc-123",
            workflow_type="translation",
            target_lang="en-rUS"
        )
        # ... 작업 수행 ...
        context.detach(token)  # 완료 후 정리
    """
    ctx = baggage.set_baggage("session.id", str(session_id))
    logger.info(f"{Colors.GREEN}Session ID '{session_id}' 텔레메트리 컨텍스트에 연결됨{Colors.END}")

    if user_type:
        ctx = baggage.set_baggage("user.type", user_type, context=ctx)
        logger.info(f"{Colors.GREEN}User Type '{user_type}' 텔레메트리 컨텍스트에 연결됨{Colors.END}")

    if workflow_type:
        ctx = baggage.set_baggage("workflow.type", workflow_type, context=ctx)
        logger.info(f"{Colors.GREEN}Workflow Type '{workflow_type}' 텔레메트리 컨텍스트에 연결됨{Colors.END}")

    if target_lang:
        ctx = baggage.set_baggage("target.lang", target_lang, context=ctx)
        logger.info(f"{Colors.GREEN}Target Lang '{target_lang}' 텔레메트리 컨텍스트에 연결됨{Colors.END}")

    return context.attach(ctx)


def get_session_id() -> Optional[str]:
    """현재 컨텍스트 baggage에서 세션 ID를 가져옵니다"""
    return baggage.get_baggage("session.id")


# =============================================================================
# Tracer 팩토리
# =============================================================================

def get_tracer(
    module_name: Optional[str] = None,
    version: Optional[str] = None
) -> trace.Tracer:
    """
    번역 에이전트용 OpenTelemetry tracer를 가져옵니다.

    환경 변수를 통해 설정:
    - TRACER_MODULE_NAME: 모듈 이름 (기본값: "translation_agent")
    - TRACER_LIBRARY_VERSION: 버전 (기본값: "1.0.0")

    Args:
        module_name: 모듈 이름 재정의
        version: 버전 재정의

    Returns:
        OpenTelemetry Tracer 인스턴스

    Example:
        tracer = get_tracer()
        with tracer.start_as_current_span("translate") as span:
            # ... 작업 수행 ...
    """
    return trace.get_tracer(
        instrumenting_module_name=module_name or os.getenv(
            "TRACER_MODULE_NAME", DEFAULT_TRACER_MODULE_NAME
        ),
        instrumenting_library_version=version or os.getenv(
            "TRACER_LIBRARY_VERSION", DEFAULT_TRACER_VERSION
        )
    )


# =============================================================================
# 스팬 헬퍼
# =============================================================================

def add_span_event(
    span: trace.Span,
    event_name: str,
    attributes: Optional[Dict[str, Any]] = None
) -> None:
    """
    지정된 스팬에 이벤트를 추가합니다.

    이벤트는 스팬 내에서 타임스탬프가 찍힌 주석으로,
    중요한 발생을 기록하는 데 유용합니다.

    Args:
        span: 이벤트를 추가할 OpenTelemetry 스팬
        event_name: 이벤트 이름 (예: "input_message", "response")
        attributes: 속성 딕셔너리 (str, bool, int, float 값)

    Example:
        with tracer.start_as_current_span("translate") as span:
            add_span_event(span, "input_message", {"text": source_text})
            result = translate(source_text)
            add_span_event(span, "response", {"text": result, "length": len(result)})
    """
    if span and span.is_recording():
        # 속성 값이 원시 타입인지 확인
        safe_attrs = {}
        if attributes:
            for key, value in attributes.items():
                if isinstance(value, (str, bool, int, float)):
                    safe_attrs[key] = value
                else:
                    safe_attrs[key] = str(value)[:1000]  # 긴 문자열 잘라내기

        span.add_event(event_name, safe_attrs)
    else:
        logger.warning(f"이벤트를 위한 유효하지 않거나 기록 중이 아닌 스팬: {event_name}")


def set_span_attribute(
    span: trace.Span,
    key: str,
    value: Any
) -> None:
    """
    지정된 스팬에 속성을 설정합니다.

    속성은 스팬을 설명하는 키-값 쌍입니다.

    Args:
        span: OpenTelemetry 스팬
        key: 속성 키
        value: 속성 값 (str, bool, int, float)

    Example:
        with tracer.start_as_current_span("translate") as span:
            set_span_attribute(span, "source_lang", "ko")
            set_span_attribute(span, "target_lang", "en-rUS")
            set_span_attribute(span, "input_length", len(text))
    """
    if span and span.is_recording():
        # 값이 원시 타입인지 확인
        if isinstance(value, (str, bool, int, float)):
            span.set_attribute(key, value)
        else:
            span.set_attribute(key, str(value)[:1000])
    else:
        logger.warning(f"속성을 위한 유효하지 않거나 기록 중이 아닌 스팬: {key}")


def set_span_status(
    span: trace.Span,
    success: bool,
    message: Optional[str] = None
) -> None:
    """
    스팬의 상태를 설정합니다.

    Args:
        span: OpenTelemetry 스팬
        success: 작업 성공 여부
        message: 선택적 상태 메시지 (오류용)

    Example:
        with tracer.start_as_current_span("evaluate") as span:
            try:
                result = evaluate(translation)
                set_span_status(span, True)
            except Exception as e:
                set_span_status(span, False, str(e))
                raise
    """
    if span and span.is_recording():
        if success:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, message or "Error"))


def record_exception(span: trace.Span, exception: Exception) -> None:
    """
    스팬에 예외를 기록합니다.

    Args:
        span: OpenTelemetry 스팬
        exception: 기록할 예외

    Example:
        with tracer.start_as_current_span("translate") as span:
            try:
                result = translate(text)
            except Exception as e:
                record_exception(span, e)
                raise
    """
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


# =============================================================================
# 번역 전용 스팬 데코레이터
# =============================================================================

@contextmanager
def trace_agent(
    agent_name: str,
    tracer: Optional[trace.Tracer] = None
):
    """
    에이전트 실행을 트레이싱하기 위한 컨텍스트 매니저.

    에이전트용 스팬을 생성하고 입출력 이벤트를 기록하기 위한
    헬퍼를 제공합니다.

    Args:
        agent_name: 에이전트 이름 (예: "translator", "accuracy_evaluator")
        tracer: 선택적 tracer (제공하지 않으면 기본값 사용)

    Yields:
        (span, event_recorder) 튜플

    Example:
        with trace_agent("translator") as (span, record):
            record("input", {"text": source_text})
            result = translator(source_text)
            record("output", {"text": result, "score": 4})
    """
    if tracer is None:
        tracer = get_tracer()

    with tracer.start_as_current_span(agent_name) as span:
        def record_event(event_type: str, attributes: Dict[str, Any] = None):
            add_span_event(span, event_type, attributes)

        try:
            yield span, record_event
            set_span_status(span, True)
        except Exception as e:
            record_exception(span, e)
            raise


@contextmanager
def trace_workflow(
    workflow_name: str,
    session_id: Optional[str] = None,
    tracer: Optional[trace.Tracer] = None
):
    """
    전체 워크플로우를 트레이싱하기 위한 컨텍스트 매니저.

    세션 컨텍스트를 설정하고 워크플로우용 루트 스팬을 생성합니다.

    Args:
        workflow_name: 워크플로우 이름 (예: "translation_pipeline")
        session_id: 선택적 세션 ID (제공하지 않으면 자동 생성)
        tracer: 선택적 tracer (제공하지 않으면 기본값 사용)

    Yields:
        (span, session_id) 튜플

    Example:
        with trace_workflow("translation_pipeline") as (span, session_id):
            set_span_attribute(span, "source_lang", "ko")
            set_span_attribute(span, "target_lang", "en-rUS")

            with trace_agent("translator") as (agent_span, record):
                result = translate(text)
    """
    import uuid

    if tracer is None:
        tracer = get_tracer()

    if session_id is None:
        session_id = str(uuid.uuid4())

    # 세션 컨텍스트 설정
    token = set_session_context(session_id, workflow_type=workflow_name)

    try:
        with tracer.start_as_current_span(workflow_name) as span:
            set_span_attribute(span, "session.id", session_id)

            try:
                yield span, session_id
                set_span_status(span, True)
            except Exception as e:
                record_exception(span, e)
                raise
    finally:
        context.detach(token)


# =============================================================================
# 노드 로깅 헬퍼 (프로덕션 패턴에서 가져옴)
# =============================================================================

def log_node_start(node_name: str) -> None:
    """
    노드 실행 시작을 로깅합니다.

    Args:
        node_name: 노드 이름 (예: "Translator", "Evaluator")
    """
    print()  # 로그 전 줄바꿈 추가
    logger.info(f"{Colors.GREEN}===== {node_name} 시작 ====={Colors.END}")


def log_node_complete(node_name: str, shared_state: Optional[Dict] = None) -> None:
    """
    노드 완료를 로깅합니다.

    shared_state가 제공되고 token_usage를 포함하면
    현재 토큰 사용량 요약을 출력합니다.

    Args:
        node_name: 노드 이름
        shared_state: token_usage를 포함하는 선택적 공유 상태
    """
    print()  # 로그 전 줄바꿈 추가
    logger.info(f"{Colors.GREEN}===== {node_name} 완료 ====={Colors.END}")

    # 토큰 사용량이 있으면 출력
    if shared_state:
        from .strands_utils import TokenTracker
        TokenTracker.print_current(shared_state)


# =============================================================================
# 비용 계산 헬퍼
# =============================================================================

def calculate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0
) -> float:
    """
    모델 호출에 대한 예상 비용(USD)을 계산합니다.

    Args:
        model_id: 모델 ID (예: "claude-opus-4-5")
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
        cache_read_tokens: 캐시 읽기 토큰 수 (90% 할인)
        cache_write_tokens: 캐시 쓰기 토큰 수 (25% 추가)

    Returns:
        예상 비용 (USD)

    Example:
        cost = calculate_cost(
            model_id="claude-opus-4-5",
            input_tokens=500,
            output_tokens=200,
            cache_read_tokens=400
        )
        print(f"비용: ${cost:.4f}")
    """
    # 모델 ID 정규화
    model_key = "default"
    if "opus" in model_id.lower():
        model_key = "claude-opus-4-5"
    elif "sonnet" in model_id.lower():
        model_key = "claude-sonnet-4-5"

    pricing = MODEL_PRICING.get(model_key, MODEL_PRICING["default"])

    cost = (
        (input_tokens / 1_000_000) * pricing["input"] +
        (output_tokens / 1_000_000) * pricing["output"] +
        (cache_read_tokens / 1_000_000) * pricing["cache_read"] +
        (cache_write_tokens / 1_000_000) * pricing["cache_write"]
    )

    return round(cost, 6)


# =============================================================================
# 내보내기
# =============================================================================

__all__ = [
    # 상수
    "Colors",
    "MODEL_PRICING",
    # 세션 컨텍스트
    "set_session_context",
    "get_session_id",
    # Tracer
    "get_tracer",
    # 스팬 헬퍼
    "add_span_event",
    "set_span_attribute",
    "set_span_status",
    "record_exception",
    # 컨텍스트 매니저
    "trace_agent",
    "trace_workflow",
    # 노드 로깅
    "log_node_start",
    "log_node_complete",
    # 비용
    "calculate_cost",
]
