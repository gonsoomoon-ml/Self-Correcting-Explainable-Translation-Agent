"""
Strands Agent 유틸리티 - BedrockModel 및 프롬프트 캐싱을 통한 Strands SDK 통합

sample-deep-insight/self-hosted의 프로덕션 검증 패턴 기반.

번역 파이프라인의 모든 LLM 상호작용에 사용됩니다.
원시 boto3 Bedrock 클라이언트를 Strands Agent로 대체:
- 간편한 에이전트 생성
- 프롬프트 캐싱 (캐시된 프롬프트 비용 90% 절감)
- 스로틀링 감지를 통한 자동 재시도 및 오류 처리
- 스트리밍 지원
"""

import logging
import traceback
import asyncio
import yaml
import os
import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from contextlib import contextmanager

from strands import Agent
from strands.models import BedrockModel
from strands.types.content import SystemContentBlock
from strands.types.exceptions import EventLoopException
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

# OpenTelemetry imports for AgentCore Observability
try:
    from opentelemetry import trace, context, baggage
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


logger = logging.getLogger(__name__)


# =============================================================================
# AgentCore Observability (OpenTelemetry Integration)
# =============================================================================

def get_tracer(name: str = "translation-agent") -> Optional[Any]:
    """
    OpenTelemetry Tracer 가져오기.

    OTEL이 설치되지 않은 경우 None 반환.
    """
    if not OTEL_AVAILABLE:
        return None
    return trace.get_tracer(name)


def generate_session_id() -> str:
    """고유 세션 ID 생성"""
    return str(uuid.uuid4())


@contextmanager
def observability_session(
    session_id: Optional[str] = None,
    workflow_name: str = "translation",
    metadata: Optional[Dict[str, str]] = None
):
    """
    AgentCore Observability 세션 컨텍스트 매니저.

    OpenTelemetry baggage를 사용하여 세션 컨텍스트를 전파합니다.

    Args:
        session_id: 세션 ID (없으면 자동 생성)
        workflow_name: 워크플로우 이름
        metadata: 추가 메타데이터

    Example:
        with observability_session(workflow_name="translation") as session:
            result = await graph.run(unit)
            # 모든 OTEL spans에 session_id가 자동 전파됨
    """
    if not OTEL_AVAILABLE:
        # OTEL 없으면 그냥 실행
        yield {"session_id": session_id or generate_session_id()}
        return

    session_id = session_id or generate_session_id()

    # Baggage에 세션 정보 설정
    ctx = baggage.set_baggage("session.id", session_id)
    ctx = baggage.set_baggage("workflow.name", workflow_name, context=ctx)

    if metadata:
        for key, value in metadata.items():
            ctx = baggage.set_baggage(f"custom.{key}", value, context=ctx)

    token = context.attach(ctx)

    try:
        tracer = get_tracer()
        if tracer:
            with tracer.start_as_current_span(
                f"workflow.{workflow_name}",
                attributes={
                    "session.id": session_id,
                    "workflow.name": workflow_name,
                    **(metadata or {})
                }
            ) as span:
                yield {
                    "session_id": session_id,
                    "span": span,
                    "tracer": tracer
                }
        else:
            yield {"session_id": session_id}
    finally:
        context.detach(token)


def add_span_event(
    name: str,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    현재 span에 이벤트 추가.

    Args:
        name: 이벤트 이름
        attributes: 이벤트 속성
    """
    if not OTEL_AVAILABLE:
        return

    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes=attributes or {})


def set_span_attributes(attributes: Dict[str, Any]):
    """
    현재 span에 속성 추가.

    Args:
        attributes: 추가할 속성 딕셔너리
    """
    if not OTEL_AVAILABLE:
        return

    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(exception: Exception):
    """
    현재 span에 예외 기록.

    Args:
        exception: 기록할 예외
    """
    if not OTEL_AVAILABLE:
        return

    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


# =============================================================================
# 설정
# =============================================================================

@dataclass
class ModelConfig:
    """특정 모델 역할에 대한 설정"""
    model_id: str
    max_tokens: int = 2000
    temperature: float = 0.1
    description: str = ""


@dataclass
class StrandsConfig:
    """전체 Strands 설정"""
    region: str = "us-west-2"
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    retry_max_attempts: int = 50
    timeout_seconds: int = 900


def load_config(config_path: Optional[str] = None) -> StrandsConfig:
    """
    models.yaml에서 설정 로드

    Args:
        config_path: models.yaml 경로. 기본값은 config/models.yaml

    Returns:
        모델 설정이 포함된 StrandsConfig
    """
    if config_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(base_dir, "config", "models.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"설정 파일을 찾을 수 없음: {config_path}, 기본값 사용")
        return _default_config()

    # 모델 파싱
    models = {}
    for role, model_cfg in raw_config.get("models", {}).items():
        models[role] = ModelConfig(
            model_id=model_cfg["model_id"],
            max_tokens=model_cfg.get("max_tokens", 2000),
            temperature=model_cfg.get("temperature", 0.1),
            description=model_cfg.get("description", "")
        )

    # 재시도 설정 파싱
    retry_cfg = raw_config.get("retry", {})

    return StrandsConfig(
        region=raw_config.get("region", "us-west-2"),
        models=models,
        retry_max_attempts=retry_cfg.get("max_attempts", 50),
        timeout_seconds=900
    )


def _default_config() -> StrandsConfig:
    """기본 설정 반환"""
    return StrandsConfig(
        region="us-west-2",
        models={
            "translator": ModelConfig(
                model_id="us.anthropic.claude-opus-4-5-20250514-v1:0",
                max_tokens=2000,
                temperature=0.3
            ),
            "backtranslator": ModelConfig(
                model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0",
                max_tokens=1000,
                temperature=0.1
            ),
            "accuracy_evaluator": ModelConfig(
                model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0",
                max_tokens=1500,
                temperature=0.1
            ),
            "compliance_evaluator": ModelConfig(
                model_id="us.anthropic.claude-sonnet-4-5-20250514-v1:0",
                max_tokens=1500,
                temperature=0.1
            ),
            "quality_evaluator": ModelConfig(
                model_id="us.anthropic.claude-opus-4-5-20250514-v1:0",
                max_tokens=1500,
                temperature=0.1
            )
        }
    )


# 싱글톤 설정 인스턴스
_config: Optional[StrandsConfig] = None


def get_config(config_path: Optional[str] = None) -> StrandsConfig:
    """설정 싱글톤 가져오기 또는 로드"""
    global _config
    if _config is None:
        _config = load_config(config_path)
    return _config


# =============================================================================
# 모델 및 에이전트 생성 (프로덕션 검증 패턴)
# =============================================================================

def get_model(
    role: str,
    streaming: bool = True,
    tool_cache: bool = False,
    enable_reasoning: bool = False,
    config: Optional[StrandsConfig] = None
) -> BedrockModel:
    """
    특정 역할에 대한 BedrockModel 가져오기.

    sample-deep-insight/self-hosted의 프로덕션 패턴 기반.

    Args:
        role: 모델 역할 (translator, backtranslator, accuracy_evaluator 등)
        streaming: 스트리밍 활성화 (기본값: True)
        tool_cache: 도구 캐싱 활성화 (기본값: False)
        enable_reasoning: 확장 사고 모드 활성화 (기본값: False)
        config: 선택적 설정 오버라이드

    Returns:
        설정된 BedrockModel 인스턴스

    Example:
        model = get_model("translator")
        model = get_model("accuracy_evaluator", streaming=False)
    """
    if config is None:
        config = get_config()

    if role not in config.models:
        available = list(config.models.keys())
        raise ValueError(f"알 수 없는 역할: {role}. 사용 가능: {available}")

    model_config = config.models[role]

    # 프로덕션 패턴: MaxTokensReachedException 방지를 위해 max_tokens=64000
    # Temperature: 추론 모드에서는 1, 그 외에는 설정값 사용
    llm = BedrockModel(
        model_id=model_config.model_id,
        streaming=streaming,
        cache_tools="default" if tool_cache else None,
        max_tokens=64000,  # MaxTokensReachedException 방지를 위한 프로덕션 값
        stop_sequences=["\n\nHuman"],
        temperature=1 if enable_reasoning else model_config.temperature,
        additional_request_fields={
            "thinking": {
                "type": "enabled" if enable_reasoning else "disabled",
                **({"budget_tokens": 8192} if enable_reasoning else {}),
            }
        },
        boto_client_config=BotoConfig(
            read_timeout=config.timeout_seconds,
            connect_timeout=config.timeout_seconds,
            retries=dict(max_attempts=config.retry_max_attempts, mode="adaptive")
        )
    )

    return llm


def get_agent(
    role: str,
    system_prompt: str,
    agent_name: Optional[str] = None,
    prompt_cache: bool = True,
    cache_type: str = "default",
    tools: Optional[List] = None,
    streaming: bool = True,
    tool_cache: bool = False,
    enable_reasoning: bool = False,
    config: Optional[StrandsConfig] = None
) -> Agent:
    """
    프롬프트 캐싱을 지원하는 Strands Agent 생성.

    sample-deep-insight/self-hosted의 프로덕션 패턴 기반.

    Args:
        role: 모델 선택을 위한 역할
        system_prompt: 시스템 프롬프트 텍스트
        agent_name: 로깅용 에이전트 이름 (기본값: role)
        prompt_cache: 프롬프트 캐싱 활성화 (기본값: True)
        cache_type: 캐시 유형 - "default" 또는 "ephemeral" (기본값: "default")
        tools: 에이전트용 도구 목록 (선택)
        streaming: 스트리밍 활성화 (기본값: True)
        tool_cache: 도구 캐싱 활성화 (기본값: False)
        enable_reasoning: 확장 사고 모드 활성화 (기본값: False)
        config: 선택적 설정 오버라이드

    Returns:
        설정된 Strands Agent 인스턴스

    Example:
        # 프롬프트 캐싱을 사용하는 간단한 에이전트
        agent = get_agent(
            role="translator",
            system_prompt="당신은 전문 번역가입니다..."
        )

        # 캐싱 없는 에이전트
        agent = get_agent(
            role="backtranslator",
            system_prompt="한국어로 역번역하세요...",
            prompt_cache=False
        )

        # 도구가 있는 에이전트
        agent = get_agent(
            role="accuracy_evaluator",
            system_prompt="번역 정확성을 평가하세요...",
            tools=[glossary_tool, reference_tool]
        )
    """
    if agent_name is None:
        agent_name = role

    # 역할에 대한 모델 가져오기
    model = get_model(
        role=role,
        streaming=streaming,
        tool_cache=tool_cache,
        enable_reasoning=enable_reasoning,
        config=config
    )

    # 캐싱이 활성화된 경우 시스템 프롬프트 구성 (프로덕션 패턴)
    if prompt_cache:
        logger.info(f"[{agent_name.upper()}] 프롬프트 캐시 활성화 (type={cache_type})")
        system_prompt_content = [
            SystemContentBlock(text=system_prompt),
            SystemContentBlock(cachePoint={"type": cache_type})
        ]
    else:
        logger.info(f"[{agent_name.upper()}] 프롬프트 캐시 비활성화")
        system_prompt_content = system_prompt

    if tool_cache:
        logger.info(f"[{agent_name.upper()}] 도구 캐시 활성화")

    # 에이전트 생성 (프로덕션 패턴: 비동기 이터레이터용 callback_handler=None)
    agent = Agent(
        model=model,
        system_prompt=system_prompt_content,
        tools=tools,
        callback_handler=None  # 스트리밍용 비동기 이터레이터 사용
    )

    return agent


def create_system_prompt_with_cache(
    system_prompt: str,
    cache_type: str = "default"
) -> List[SystemContentBlock]:
    """
    캐시 포인트가 있는 시스템 프롬프트 콘텐츠 블록 생성.

    커스텀 에이전트 설정을 위해 수동으로 시스템 프롬프트를
    구성해야 할 때 유용합니다.

    Args:
        system_prompt: 시스템 프롬프트 텍스트
        cache_type: "default" (영구) 또는 "ephemeral" (5분)

    Returns:
        Agent에서 사용할 SystemContentBlock 목록

    Example:
        prompt_blocks = create_system_prompt_with_cache(
            "당신은 번역가입니다...",
            cache_type="default"
        )
        agent = Agent(model=model, system_prompt=prompt_blocks)
    """
    return [
        SystemContentBlock(text=system_prompt),
        SystemContentBlock(cachePoint={"type": cache_type})
    ]


# =============================================================================
# 상태 관리 헬퍼 (프로덕션 패턴)
# =============================================================================

def get_agent_state(agent: Agent, key: str, default_value: Any = None) -> Any:
    """
    Strands Agent 상태에서 값을 안전하게 가져오기.

    Args:
        agent: Strands Agent 인스턴스
        key: 가져올 상태 키
        default_value: 키가 없을 경우 기본값

    Returns:
        상태 값 또는 기본값
    """
    value = agent.state.get(key)
    if value is None:
        return default_value
    return value


def get_agent_state_all(agent: Agent) -> Dict[str, Any]:
    """Strands Agent의 모든 상태 가져오기"""
    return agent.state.get()


def update_agent_state(agent: Agent, key: str, value: Any) -> None:
    """Strands Agent의 단일 상태 키 업데이트"""
    agent.state.set(key, value)


def update_agent_state_all(target_agent: Agent, source_agent: Agent) -> Agent:
    """소스 에이전트에서 대상 에이전트로 상태 복사"""
    source_state = source_agent.state.get()
    if source_state:
        for key, value in source_state.items():
            target_agent.state.set(key, value)
    return target_agent


# =============================================================================
# 재시도 기능이 있는 스트리밍 (프로덕션 검증 스로틀링 처리)
# =============================================================================

async def _retry_agent_streaming(
    agent: Agent,
    message: str,
    max_attempts: int = 5,
    base_delay: int = 10
):
    """
    스로틀링 재시도 로직이 있는 에이전트 스트리밍.

    sample-deep-insight/self-hosted의 프로덕션 검증 패턴.

    Args:
        agent: Strands 에이전트 인스턴스
        message: 에이전트에 보낼 메시지
        max_attempts: 최대 재시도 횟수
        base_delay: 지수 백오프를 위한 기본 지연 시간(초)

    Yields:
        원시 에이전트 스트리밍 이벤트
    """
    for attempt in range(max_attempts):
        try:
            agent_stream = agent.stream_async(message)
            async for event in agent_stream:
                yield event
            # 여기까지 왔다면 스트리밍 성공
            return

        except (EventLoopException, ClientError) as e:
            # 스로틀링 오류인지 확인
            is_throttling = False

            if isinstance(e, EventLoopException):
                error_msg = str(e).lower()
                is_throttling = 'throttling' in error_msg or 'too many requests' in error_msg
            elif isinstance(e, ClientError):
                error_code = e.response.get('Error', {}).get('Code', '')
                is_throttling = error_code == 'ThrottlingException'

            # 스로틀링 오류에 대해 재시도
            if is_throttling and attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)  # 지수 백오프
                logger.info(f"스로틀링 감지 - 재시도 {attempt + 1}/{max_attempts}, {delay}초 대기 중...")
                await asyncio.sleep(delay)
                continue
            else:
                if attempt == max_attempts - 1:
                    logger.error(f"스트리밍 오류 (시도 {attempt + 1}/{max_attempts}): {e}")
                    logger.error(traceback.format_exc())
                    raise
                else:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue

        except Exception as e:
            logger.error(f"스트리밍 중 예상치 못한 오류: {e}")
            logger.error(traceback.format_exc())
            raise


# =============================================================================
# 에이전트 실행 헬퍼
# =============================================================================

def extract_usage_from_agent(agent: Agent) -> Dict[str, int]:
    """
    에이전트의 이벤트 루프 메트릭에서 토큰 사용량 추출.

    sample-deep-insight/self-hosted의 프로덕션 패턴.

    Args:
        agent: 실행 후 Strands Agent 인스턴스

    Returns:
        토큰 사용량 딕셔너리:
        - input_tokens: 일반 입력 토큰
        - output_tokens: 출력 토큰
        - total_tokens: 총 토큰
        - cache_read_input_tokens: 읽은 캐시 토큰 (90% 할인)
        - cache_write_input_tokens: 캐시에 쓴 토큰 (25% 추가)
    """
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_write_input_tokens": 0
    }

    try:
        if hasattr(agent, 'event_loop_metrics'):
            metrics = agent.event_loop_metrics
            if hasattr(metrics, 'accumulated_usage'):
                accumulated = metrics.accumulated_usage
                usage["input_tokens"] = accumulated.get("inputTokens", 0)
                usage["output_tokens"] = accumulated.get("outputTokens", 0)
                usage["total_tokens"] = accumulated.get("totalTokens", 0)
                usage["cache_read_input_tokens"] = accumulated.get("cacheReadInputTokens", 0)
                usage["cache_write_input_tokens"] = accumulated.get("cacheWriteInputTokens", 0)
    except Exception as e:
        logger.warning(f"사용량 추출 실패: {e}")

    return usage


async def run_agent_async(
    agent: Agent,
    message: str,
    collect_response: bool = True,
    use_retry: bool = True
) -> Dict[str, Any]:
    """
    스트리밍 및 선택적 재시도로 에이전트를 비동기 실행.

    Args:
        agent: Strands Agent 인스턴스
        message: 보낼 사용자 메시지
        collect_response: 전체 응답 텍스트 수집 (기본값: True)
        use_retry: 스로틀링 재시도 로직 사용 (기본값: True)

    Returns:
        딕셔너리:
        - text: 전체 응답 텍스트
        - usage: 토큰 사용량 통계

    Example:
        agent = get_agent("translator", system_prompt="...")
        result = await run_agent_async(agent, "번역: 안녕하세요")
        print(result["text"])
        print(result["usage"])
    """
    response_text = ""

    if use_retry:
        async for event in _retry_agent_streaming(agent, message):
            if collect_response and "data" in event:
                response_text += event["data"]
    else:
        async for event in agent.stream_async(message):
            if collect_response and "data" in event:
                response_text += event["data"]

    usage = extract_usage_from_agent(agent)

    return {
        "text": response_text,
        "usage": usage
    }


def run_agent_sync(
    agent: Agent,
    message: str
) -> Dict[str, Any]:
    """
    에이전트를 동기 실행.

    Args:
        agent: Strands Agent 인스턴스
        message: 보낼 사용자 메시지

    Returns:
        딕셔너리:
        - text: 전체 응답 텍스트
        - usage: 토큰 사용량 통계

    Example:
        agent = get_agent("translator", system_prompt="...")
        result = run_agent_sync(agent, "번역: 안녕하세요")
        print(result["text"])
    """
    response = agent(message)

    # 응답에서 텍스트 추출 (프로덕션 패턴)
    text = ""
    if hasattr(response, 'message') and response.message:
        content = response.message.get("content", [])
        if content:
            text = content[-1].get("text", "")

    usage = extract_usage_from_agent(agent)

    return {
        "text": text,
        "usage": usage
    }


def parse_response_text(response) -> Dict[str, str]:
    """
    추론이 있는 경우를 포함하여 에이전트 응답에서 텍스트 파싱.

    sample-deep-insight/self-hosted의 프로덕션 패턴.

    Args:
        response: 에이전트 응답 객체

    Returns:
        딕셔너리:
        - text: 메인 응답 텍스트
        - reasoning: 추론 텍스트 (추론 모드 활성화 시)
        - signature: 추론 서명 (있는 경우)
    """
    output = {}

    if len(response.message["content"]) == 2:  # 추론 있음
        reasoning_content = response.message["content"][0].get("reasoningContent", {})
        reasoning_text = reasoning_content.get("reasoningText", {})
        output["reasoning"] = reasoning_text.get("text", "")
        output["signature"] = reasoning_text.get("signature", "")

    output["text"] = response.message["content"][-1].get("text", "")

    return output


# =============================================================================
# 토큰 추적 (프로덕션 검증 패턴)
# =============================================================================

class TokenTracker:
    """
    에이전트 간 토큰 사용량 추적 및 보고를 위한 헬퍼 클래스.

    sample-deep-insight/self-hosted의 프로덕션 검증 패턴.

    유용한 경우:
    - 번역 파이프라인에서 여러 에이전트 간 비용 추적
    - 프롬프트 캐싱 작동 확인 (cache_read vs cache_write)
    - 최적화를 위한 에이전트 및 모델별 사용량 분석
    - 배치 번역에 대한 비용 보고서 생성

    Example:
        shared_state = {}
        TokenTracker.initialize(shared_state)

        # 각 에이전트 호출 후
        usage = extract_usage_from_agent(agent)
        event = {
            "event_type": "usage_metadata",
            "agent_name": "translator",
            "model_id": "claude-opus-4-5",
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
            "cache_read_input_tokens": usage["cache_read_input_tokens"],
            "cache_write_input_tokens": usage["cache_write_input_tokens"],
        }
        TokenTracker.accumulate(event, shared_state)

        # 워크플로우 종료 시
        TokenTracker.print_summary(shared_state)
    """

    # 터미널 출력용 ANSI 색상 코드
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    END = '\033[0m'

    @staticmethod
    def initialize(shared_state: Dict[str, Any]) -> None:
        """공유 상태에 토큰 추적 구조 초기화 (없는 경우)."""
        if 'token_usage' not in shared_state:
            shared_state['token_usage'] = {
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_tokens': 0,
                'cache_read_input_tokens': 0,   # 캐시 히트 (90% 할인)
                'cache_write_input_tokens': 0,  # 캐시 생성 (25% 추가 비용)
                'by_agent': {}
            }

    @staticmethod
    def accumulate(event: Dict[str, Any], shared_state: Dict[str, Any]) -> None:
        """메타데이터 이벤트의 토큰 사용량을 공유 상태에 누적."""
        if event.get("event_type") == "usage_metadata":
            TokenTracker.initialize(shared_state)
            usage = shared_state['token_usage']

            input_tokens = event.get('input_tokens', 0)
            output_tokens = event.get('output_tokens', 0)
            total_tokens = event.get('total_tokens', 0)
            cache_read = event.get('cache_read_input_tokens', 0)
            cache_write = event.get('cache_write_input_tokens', 0)

            # 총 토큰 누적
            usage['total_input_tokens'] += input_tokens
            usage['total_output_tokens'] += output_tokens
            usage['total_tokens'] += total_tokens
            usage['cache_read_input_tokens'] += cache_read
            usage['cache_write_input_tokens'] += cache_write

            # model_id와 함께 에이전트별 추적
            agent_name = event.get('agent_name')
            model_id = event.get('model_id', 'unknown')

            if agent_name:
                if agent_name not in usage['by_agent']:
                    usage['by_agent'][agent_name] = {
                        'input': 0,
                        'output': 0,
                        'cache_read': 0,
                        'cache_write': 0,
                        'model_id': model_id
                    }
                usage['by_agent'][agent_name]['input'] += input_tokens
                usage['by_agent'][agent_name]['output'] += output_tokens
                usage['by_agent'][agent_name]['cache_read'] += cache_read
                usage['by_agent'][agent_name]['cache_write'] += cache_write
                usage['by_agent'][agent_name]['model_id'] = model_id

    @staticmethod
    def accumulate_from_agent(
        agent: Agent,
        agent_name: str,
        shared_state: Dict[str, Any]
    ) -> None:
        """
        에이전트에서 직접 사용량을 누적하는 편의 메서드.

        Args:
            agent: 실행 후 Strands Agent 인스턴스
            agent_name: 추적용 에이전트 이름
            shared_state: 공유 상태 딕셔너리
        """
        usage = extract_usage_from_agent(agent)
        model_id = agent.model.config.get('model_id', 'unknown') if hasattr(agent, 'model') else 'unknown'

        event = {
            "event_type": "usage_metadata",
            "agent_name": agent_name,
            "model_id": model_id,
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "total_tokens": usage["total_tokens"],
            "cache_read_input_tokens": usage["cache_read_input_tokens"],
            "cache_write_input_tokens": usage["cache_write_input_tokens"],
        }
        TokenTracker.accumulate(event, shared_state)

    @staticmethod
    def get_usage(shared_state: Dict[str, Any]) -> Dict[str, Any]:
        """현재 토큰 사용량 딕셔너리 가져오기."""
        return shared_state.get('token_usage', {})

    @staticmethod
    def get_total_tokens(shared_state: Dict[str, Any]) -> int:
        """사용된 총 토큰 가져오기."""
        return shared_state.get('token_usage', {}).get('total_tokens', 0)

    @staticmethod
    def get_cache_savings_ratio(shared_state: Dict[str, Any]) -> float:
        """
        캐시 절감 비율 계산.

        Returns:
            캐시 히트 비율을 나타내는 0~1 사이의 Float.
            높을수록 좋음 (더 많은 캐시 히트 = 더 많은 절감).
        """
        usage = shared_state.get('token_usage', {})
        cache_read = usage.get('cache_read_input_tokens', 0)
        cache_write = usage.get('cache_write_input_tokens', 0)
        total_cache = cache_read + cache_write

        if total_cache == 0:
            return 0.0
        return cache_read / total_cache

    @staticmethod
    def print_current(shared_state: Dict[str, Any]) -> None:
        """모델 정보와 함께 현재 누적 토큰 사용량 출력."""
        token_usage = shared_state.get('token_usage', {})
        if token_usage and token_usage.get('total_tokens', 0) > 0:
            total_input = token_usage.get('total_input_tokens', 0)
            total_output = token_usage.get('total_output_tokens', 0)
            total = token_usage.get('total_tokens', 0)
            cache_read = token_usage.get('cache_read_input_tokens', 0)
            cache_write = token_usage.get('cache_write_input_tokens', 0)

            # 사용된 고유 모델 가져오기
            by_agent = token_usage.get('by_agent', {})
            models_used = set()
            for agent_data in by_agent.values():
                if 'model_id' in agent_data:
                    models_used.add(agent_data['model_id'])

            print(f"{TokenTracker.CYAN}>>> 누적 토큰 (총: {total:,}):{TokenTracker.END}")
            if models_used:
                print(f"{TokenTracker.CYAN}    모델: {', '.join(sorted(models_used))}{TokenTracker.END}")
            print(f"{TokenTracker.CYAN}    일반 입력: {total_input:,} | 캐시 읽기: {cache_read:,} (90% 할인) | 캐시 쓰기: {cache_write:,} (25% 추가) | 출력: {total_output:,}{TokenTracker.END}")

    @staticmethod
    def print_summary(shared_state: Dict[str, Any]) -> None:
        """모델 및 에이전트 분석이 포함된 상세 토큰 사용량 요약 출력."""
        print("\n" + "=" * 60)
        print("=== 토큰 사용량 요약 ===")
        print("=" * 60)

        token_usage = shared_state.get('token_usage', {})

        if not token_usage or token_usage.get('total_tokens', 0) == 0:
            print("토큰 사용량 데이터 없음")
            print("=" * 60)
            return

        total_input = token_usage.get('total_input_tokens', 0)
        total_output = token_usage.get('total_output_tokens', 0)
        total = token_usage.get('total_tokens', 0)
        cache_read = token_usage.get('cache_read_input_tokens', 0)
        cache_write = token_usage.get('cache_write_input_tokens', 0)

        # 사용된 고유 모델 가져오기
        by_agent = token_usage.get('by_agent', {})
        models_used = set()
        for agent_data in by_agent.values():
            if 'model_id' in agent_data:
                models_used.add(agent_data['model_id'])

        print(f"\n총 토큰: {total:,}")
        if models_used:
            print(f"사용된 모델: {', '.join(sorted(models_used))}")
        print(f"  - 일반 입력:    {total_input:>8,} (100% 비용)")
        print(f"  - 캐시 읽기:    {cache_read:>8,} (10% 비용 - 90% 할인)")
        print(f"  - 캐시 쓰기:    {cache_write:>8,} (125% 비용 - 25% 추가)")
        print(f"  - 출력:         {total_output:>8,}")

        # 캐시 효율성
        cache_ratio = TokenTracker.get_cache_savings_ratio(shared_state)
        print(f"\n  캐시 히트율: {cache_ratio:.1%}")

        # 모델 사용량 요약
        if by_agent:
            print("\n" + "-" * 60)
            print("모델 사용량 요약 (비용 계산용):")
            print("-" * 60)

            # 모델별 토큰 집계
            model_usage = {}
            for agent_name, usage in by_agent.items():
                model_id = usage.get('model_id', 'unknown')
                if model_id not in model_usage:
                    model_usage[model_id] = {
                        'input': 0,
                        'output': 0,
                        'cache_read': 0,
                        'cache_write': 0,
                        'agents': []
                    }
                model_usage[model_id]['input'] += usage.get('input', 0)
                model_usage[model_id]['output'] += usage.get('output', 0)
                model_usage[model_id]['cache_read'] += usage.get('cache_read', 0)
                model_usage[model_id]['cache_write'] += usage.get('cache_write', 0)
                model_usage[model_id]['agents'].append(agent_name)

            for model_id in sorted(model_usage.keys()):
                usage = model_usage[model_id]
                model_total = usage['input'] + usage['output'] + usage['cache_read'] + usage['cache_write']
                agents_str = ', '.join(usage['agents'])

                print(f"\n  [{model_id}]")
                print(f"    총: {model_total:,}")
                print(f"    - 일반 입력:    {usage['input']:>8,} (100% 비용)")
                print(f"    - 캐시 읽기:    {usage['cache_read']:>8,} (10% 비용 - 90% 할인)")
                print(f"    - 캐시 쓰기:    {usage['cache_write']:>8,} (125% 비용 - 25% 추가)")
                print(f"    - 출력:         {usage['output']:>8,}")
                print(f"    사용 에이전트: {agents_str}")

            print("\n" + "-" * 60)
            print("에이전트별 토큰 사용량:")
            print("-" * 60)

            for agent_name in sorted(by_agent.keys()):
                usage = by_agent[agent_name]
                input_tokens = usage.get('input', 0)
                output_tokens = usage.get('output', 0)
                agent_cache_read = usage.get('cache_read', 0)
                agent_cache_write = usage.get('cache_write', 0)
                agent_total = input_tokens + output_tokens + agent_cache_read + agent_cache_write
                model_id = usage.get('model_id', 'unknown')

                print(f"\n  [{agent_name}] 총: {agent_total:,}")
                print(f"    모델: {model_id}")
                print(f"    - 일반 입력:    {input_tokens:>8,} (100% 비용)")
                print(f"    - 캐시 읽기:    {agent_cache_read:>8,} (10% 비용 - 90% 할인)")
                print(f"    - 캐시 쓰기:    {agent_cache_write:>8,} (125% 비용 - 25% 추가)")
                print(f"    - 출력:         {output_tokens:>8,}")

        print("=" * 60)

    @staticmethod
    def to_dict(shared_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        JSON 직렬화를 위해 토큰 사용량을 딕셔너리로 내보내기.

        TranslationRecord 메타데이터에 저장할 때 유용.
        """
        usage = shared_state.get('token_usage', {})
        return {
            'total_input_tokens': usage.get('total_input_tokens', 0),
            'total_output_tokens': usage.get('total_output_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0),
            'cache_read_input_tokens': usage.get('cache_read_input_tokens', 0),
            'cache_write_input_tokens': usage.get('cache_write_input_tokens', 0),
            'cache_hit_ratio': TokenTracker.get_cache_savings_ratio(shared_state),
            'by_agent': usage.get('by_agent', {})
        }


# =============================================================================
# 내보내기
# =============================================================================

__all__ = [
    # 설정
    "ModelConfig",
    "StrandsConfig",
    "load_config",
    "get_config",
    # 모델 및 에이전트 생성
    "get_model",
    "get_agent",
    "create_system_prompt_with_cache",
    # 상태 관리
    "get_agent_state",
    "get_agent_state_all",
    "update_agent_state",
    "update_agent_state_all",
    # 실행
    "extract_usage_from_agent",
    "run_agent_async",
    "run_agent_sync",
    "parse_response_text",
    # 토큰 추적
    "TokenTracker",
]
