# Observability 가이드

Translation Agent를 위한 AWS CloudWatch/X-Ray Observability 연동 가이드입니다.

## 왜 Observability인가?

LLM 기반 에이전트 시스템의 고질적인 문제:

| 문제 | 영향 |
|------|------|
| **블랙박스 실행** | 어떤 에이전트가 언제 호출됐는지 모름 |
| **지연 원인 불명** | 전체 30초 중 어디서 지연됐는지 파악 불가 |
| **토큰 비용 추적 어려움** | 어떤 에이전트가 토큰을 많이 사용하는지 모름 |
| **오류 디버깅 어려움** | 5개 에이전트 중 어디서 실패했는지 추적 불가 |

**Observability 해결책:**

| 기능 | 효과 |
|------|------|
| **분산 트레이싱** | 전체 워크플로우를 스팬 트리로 시각화 |
| **지연 분석** | 각 에이전트별 실행 시간 측정 |
| **비용 추적** | 에이전트별 토큰 사용량 및 비용 집계 |
| **에러 추적** | 실패한 스팬에 예외 정보 기록 |

---

## 아키텍처에서의 위치

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              번역 파이프라인                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────────────┐    ┌──────────┐           │
│  │TRANSLATE│───▶│BACKTRANS│───▶│EVALUATE (3 병렬)│───▶│  DECIDE  │           │
│  └────┬────┘    └────┬────┘    └────────┬────────┘    └────┬─────┘           │
│       │              │                  │                  │                  │
│       └──────────────┴──────────────────┴──────────────────┘                  │
│                                    │                                          │
│                             ┌──────┴──────┐                                   │
│                             │ OTEL Spans  │                                   │
│                             │ • latency   │                                   │
│                             │ • tokens    │                                   │
│                             │ • errors    │                                   │
│                             └──────┬──────┘                                   │
│                                    │                                          │
└────────────────────────────────────┼──────────────────────────────────────────┘
                                     │ HTTPS (SigV4 자동 서명)
                                     ▼
                     ┌───────────────────────────────────────┐
                     │        AWS CloudWatch / X-Ray         │
                     │  • Transaction Search (트레이스 시각화) │
                     │  • 에이전트별 지연 분석                  │
                     │  • 토큰 비용 집계                       │
                     └───────────────────────────────────────┘
```

---

## 5분 시작

```bash
# 1. AWS 인증 (이미 되어있으면 건너뛰기)
aws configure

# 2. 환경 변수 로드
cd 01_explainable_translate_agent
source config/observability.env

# 3. 워크플로우 실행 (트레이싱 활성화)
uv run opentelemetry-instrument python test_workflow.py --input examples/single/faq.json

# 4. CloudWatch에서 확인
# https://us-west-2.console.aws.amazon.com/cloudwatch/home?region=us-west-2#transactionSearch
```

---

## 개요

이 프로젝트는 **AWS Distro for OpenTelemetry (ADOT) SDK**를 사용하여 X-Ray OTLP 엔드포인트로 트레이스를 직접 전송합니다. **CloudWatch Agent 불필요** - Collector-less 모드로 동작합니다.

```
┌─────────────────────────────────────────────────────────────┐
│                    Translation Agent                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │Translate│→ │Backtrans│→ │Evaluate │→ │ Decide  │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       └────────────┴────────────┴────────────┘              │
│                         │                                    │
│                    OTEL Spans                                │
│                         │                                    │
│              ADOT SDK (SigV4 자동 서명)                      │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS (직접 전송)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│           https://xray.{region}.amazonaws.com/v1/traces      │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │  X-Ray Console   │  │ Transaction Search│                 │
│  │  (Trace View)    │  │  (aws/spans)      │                 │
│  └──────────────────┘  └──────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## 핵심 함수 요약

| 함수 | 위치 | 용도 |
|------|------|------|
| `observability_session()` | strands_utils.py | 워크플로우 전체를 감싸는 컨텍스트 매니저 |
| `trace_workflow()` | observability.py | 루트 스팬 생성 (워크플로우 레벨) |
| `trace_agent()` | observability.py | 개별 에이전트 스팬 생성 |
| `add_span_event()` | 양쪽 | 현재 스팬에 이벤트 추가 |
| `set_span_attributes()` | strands_utils.py | 현재 스팬에 속성 추가 |
| `record_exception()` | strands_utils.py | 예외 정보 기록 |
| `TokenTracker` | strands_utils.py | 에이전트별 토큰 사용량 추적 |
| `calculate_cost()` | observability.py | 토큰 → 비용 변환 |
| `log_node_start/complete()` | observability.py | 노드 실행 로깅 |

---

## 아키텍처 선택: Collector-less vs Agent

| 항목 | Collector-less (현재) | CloudWatch Agent |
|------|----------------------|------------------|
| **추가 설치** | 없음 (pip만) | Agent 설치 필요 |
| **프로세스** | 앱 내 (인프로세스) | 별도 데몬 |
| **SigV4 인증** | ADOT SDK 자동 처리 | Agent가 처리 |
| **전송 경로** | App → X-Ray (직접) | App → Agent → X-Ray |
| **설정 파일** | 1개 (env) | 3개 (json, toml, override) |
| **복잡도** | **낮음** ✅ | 중간 |
| **권장** | EC2, 컨테이너, 로컬 | 대규모 운영 환경 |

## 빠른 시작

### 1. 환경 설치

```bash
# 프로젝트 루트에서 실행
./setup/create_env.sh
```

설치되는 OTEL 패키지:
- `aws-opentelemetry-distro` - AWS ADOT SDK (SigV4 자동 서명)
- `opentelemetry-exporter-otlp` - OTLP 프로토콜 익스포터
- `strands-agents[otel]` - Strands 에이전트 OTEL 통합

### 2. AWS 자격 증명 설정

```bash
aws configure
# AWS Access Key ID: <your-key>
# AWS Secret Access Key: <your-secret>
# Default region: us-west-2
```

필요한 IAM 권한:
- `AWSXrayWriteOnlyPolicy` - X-Ray 트레이스 전송

### 3. 워크플로우 실행

```bash
cd 01_explainable_translate_agent

# 방법 1: 환경변수 로드 후 실행 (권장)
source config/observability.env
uv run opentelemetry-instrument python test_workflow.py

# 방법 2: 한 줄로 실행
OTEL_PYTHON_DISTRO=aws_distro \
OTEL_PYTHON_CONFIGURATOR=aws_configurator \
OTEL_SERVICE_NAME=translation-agent \
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-west-2.amazonaws.com/v1/traces \
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf \
OTEL_TRACES_EXPORTER=otlp \
OTEL_METRICS_EXPORTER=none \
uv run opentelemetry-instrument python test_workflow.py
```

### 4. 트레이스 확인

- **CloudWatch Transaction Search**: https://us-west-2.console.aws.amazon.com/cloudwatch/home?region=us-west-2#transactionSearch
- **로그 그룹**: `aws/spans`

## 환경 변수 설정

### 필수 변수 (config/observability.env)

```bash
# =============================================================================
# AWS ADOT 설정 (필수 - SigV4 자동 서명)
# =============================================================================
OTEL_PYTHON_DISTRO=aws_distro
OTEL_PYTHON_CONFIGURATOR=aws_configurator

# =============================================================================
# Traces → X-Ray OTLP Endpoint (직접 전송)
# =============================================================================
OTEL_SERVICE_NAME=translation-agent
OTEL_TRACES_EXPORTER=otlp
OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-west-2.amazonaws.com/v1/traces

# =============================================================================
# Metrics (비활성화)
# =============================================================================
OTEL_METRICS_EXPORTER=none
```

### 변수 설명

| 변수 | 값 | 설명 |
|------|-----|------|
| `OTEL_PYTHON_DISTRO` | `aws_distro` | AWS ADOT 배포판 사용 |
| `OTEL_PYTHON_CONFIGURATOR` | `aws_configurator` | AWS 설정자 (SigV4 자동) |
| `OTEL_SERVICE_NAME` | `translation-agent` | CloudWatch에 표시될 서비스명 |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `https://xray.{region}.amazonaws.com/v1/traces` | X-Ray OTLP 엔드포인트 |
| `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL` | `http/protobuf` | 전송 프로토콜 |
| `OTEL_TRACES_EXPORTER` | `otlp` | OTLP 익스포터 사용 |
| `OTEL_METRICS_EXPORTER` | `none` | 메트릭 비활성화 |

### 리전별 엔드포인트

| 리전 | 엔드포인트 |
|------|-----------|
| us-west-2 | `https://xray.us-west-2.amazonaws.com/v1/traces` |
| us-east-1 | `https://xray.us-east-1.amazonaws.com/v1/traces` |
| ap-northeast-2 | `https://xray.ap-northeast-2.amazonaws.com/v1/traces` |

## 트레이스 구조

워크플로우 실행 시 생성되는 트레이스 계층:

```
workflow.translation-single (루트 스팬)
├── session.id: "550e8400-..."
├── workflow.name: "translation-single"
│
├── invoke_agent Strands Agents
│   └── chat global.anthropic.claude-opus-4-5-*
│       └── Bedrock Runtime.ConverseStream
│
├── invoke_agent Strands Agents (backtranslate)
│   └── chat global.anthropic.claude-sonnet-4-5-*
│
├── invoke_agent Strands Agents (evaluate - 병렬)
│   ├── accuracy
│   ├── compliance
│   └── quality
│
└── decide
    ├── verdict: "pass"
    └── can_publish: true
```

### 스팬 유형

| 스팬 | 설명 | 주요 속성 |
|------|------|-----------|
| `workflow.*` | 루트 스팬 | session.id, workflow.name |
| `invoke_agent Strands Agents` | 에이전트 호출 | agent.name |
| `chat global.anthropic.*` | Bedrock API 호출 | model, tokens |
| `Bedrock Runtime.ConverseStream` | 스트리밍 응답 | latency_ms |

## 코드에서 Observability 사용하기

### 세션 컨텍스트 (strands_utils.py)

`observability_session`은 워크플로우 전체를 감싸는 컨텍스트 매니저입니다:

```python
from src.utils.strands_utils import observability_session

# 기본 사용
with observability_session(
    session_id="user-123",           # 선택 (없으면 자동 생성)
    workflow_name="translation",     # 워크플로우 이름
    metadata={"user_type": "premium"}  # 추가 메타데이터 (선택)
) as session:
    print(f"Session ID: {session['session_id']}")
    # session['span'] - 루트 스팬 (OTEL 활성화 시)
    # session['tracer'] - tracer 인스턴스 (OTEL 활성화 시)
    result = await graph.run(unit)
```

### 스팬 이벤트 추가 (strands_utils.py)

현재 활성 스팬에 이벤트를 추가합니다:

```python
from src.utils.strands_utils import add_span_event

# 이벤트 추가 (현재 스팬에)
add_span_event("translation_complete", {
    "source_lang": "ko",
    "target_lang": "en"
})
```

### 스팬 속성 추가 (strands_utils.py)

현재 활성 스팬에 속성을 추가합니다:

```python
from src.utils.strands_utils import set_span_attributes

# 여러 속성 한번에 추가
set_span_attributes({
    "translation.score": 4.5,
    "translation.verdict": "pass"
})
```

### 예외 기록 (strands_utils.py)

```python
from src.utils.strands_utils import record_exception

try:
    result = await translate(text)
except Exception as e:
    record_exception(e)  # 현재 스팬에 예외 기록
    raise
```

### 에이전트 트레이싱 (observability.py)

개별 에이전트 실행을 트레이싱합니다:

```python
from src.utils.observability import trace_agent

with trace_agent("translator") as (span, record):
    record("input", {"text": source_text})      # 이벤트 기록
    result = translator(source_text)
    record("output", {"text": result, "score": 4})
```

### 워크플로우 트레이싱 (observability.py)

전체 워크플로우에 대한 루트 스팬을 생성합니다:

```python
from src.utils.observability import trace_workflow, set_span_attribute

with trace_workflow("translation_pipeline") as (span, session_id):
    set_span_attribute(span, "source_lang", "ko")
    set_span_attribute(span, "target_lang", "en-rUS")

    # 하위 에이전트 트레이싱
    with trace_agent("translator") as (agent_span, record):
        result = translate(text)
```

### 노드 로깅 (observability.py)

파이프라인 노드의 시작/완료를 로깅합니다:

```python
from src.utils.observability import log_node_start, log_node_complete

log_node_start("Translator")
# ... 노드 작업 수행 ...
log_node_complete("Translator", shared_state)  # 토큰 사용량 출력
```

## 토큰 추적 (TokenTracker)

에이전트 간 토큰 사용량을 추적합니다:

```python
from src.utils.strands_utils import TokenTracker, extract_usage_from_agent

# 초기화
shared_state = {}
TokenTracker.initialize(shared_state)

# 에이전트 실행 후 사용량 누적
agent = get_agent("translator", system_prompt="...")
result = await run_agent_async(agent, message)
TokenTracker.accumulate_from_agent(agent, "translator", shared_state)

# 현재 사용량 출력
TokenTracker.print_current(shared_state)

# 워크플로우 종료 시 요약 출력
TokenTracker.print_summary(shared_state)

# JSON으로 내보내기
usage_dict = TokenTracker.to_dict(shared_state)
```

## 트레이스 확인 방법

### 1. CloudWatch Transaction Search

1. [CloudWatch Console](https://console.aws.amazon.com/cloudwatch) 열기
2. **Transaction Search** 이동
3. 로그 그룹: `aws/spans`
4. 필터: `service.name = translation-agent`

### 2. AWS CLI로 확인

```bash
# 최근 트레이스 조회
aws logs get-log-events \
  --log-group-name "aws/spans" \
  --log-stream-name "default" \
  --region us-west-2 \
  --limit 5

# 특정 서비스 필터링
aws logs filter-log-events \
  --log-group-name "aws/spans" \
  --region us-west-2 \
  --filter-pattern '{ $.resource.attributes."service.name" = "translation-agent" }'
```

## 비용 추적

### 결과 JSON의 비용 정보

토큰 사용량과 비용이 결과 JSON에 기록됩니다:

```json
{
  "metrics": {
    "token_usage": {
      "input": 4531,
      "output": 1431,
      "cache_read": 0,
      "cache_write": 0
    },
    "cost_usd": {
      "input_cost": 0.017214,
      "output_cost": 0.02717,
      "total_cost": 0.044384
    }
  }
}
```

### 비용 계산 함수 (observability.py)

```python
from src.utils.observability import calculate_cost

cost = calculate_cost(
    model_id="claude-opus-4-5",
    input_tokens=500,
    output_tokens=200,
    cache_read_tokens=400
)
print(f"비용: ${cost:.4f}")
```

### 모델별 가격 (1M 토큰당)

| 모델 | 입력 | 출력 | 캐시 읽기 | 캐시 쓰기 |
|------|------|------|-----------|-----------|
| Claude Opus 4.5 | $15 | $75 | $1.5 (90% 할인) | $18.75 (25% 추가) |
| Claude Sonnet 4.5 | $3 | $15 | $0.3 (90% 할인) | $3.75 (25% 추가) |

## 문제 해결

### 트레이스가 CloudWatch에 없는 경우

1. **AWS 자격 증명 확인**
   ```bash
   aws sts get-caller-identity
   ```

2. **Transaction Search 활성화 확인**
   - CloudWatch → Settings → Transaction Search → Enable

3. **IAM 권한 확인**
   - `AWSXrayWriteOnlyPolicy` 정책 필요

4. **디버그 모드 활성화**
   ```bash
   export OTEL_LOG_LEVEL=debug
   uv run opentelemetry-instrument python test_workflow.py
   ```

### 일반적인 오류

| 오류 | 원인 | 해결 |
|------|------|------|
| `403 Missing Authentication Token` | SigV4 미적용 | `OTEL_PYTHON_DISTRO=aws_distro` 설정 |
| `No credentials` | AWS 자격 증명 없음 | `aws configure` 실행 |
| `OTEL_AVAILABLE = False` | 패키지 미설치 | `./setup/create_env.sh` 실행 |

### Kubernetes/ECS 경고 무시

다음 경고는 EC2에서 정상입니다 (무시 가능):
```
AwsEksResourceDetector failed: No such file or directory
AwsEcsResourceDetector failed: Missing ECS_CONTAINER_METADATA_URI
```

## 파일 구조

```
01_explainable_translate_agent/
├── config/
│   └── observability.env          # OTEL 환경 변수
├── src/utils/
│   ├── observability.py           # 핵심 OTEL 유틸리티
│   │   ├── trace_agent()          # 에이전트 트레이싱
│   │   ├── trace_workflow()       # 워크플로우 트레이싱
│   │   ├── add_span_event()       # 스팬 이벤트 (span 인자 필요)
│   │   ├── set_span_attribute()   # 스팬 속성 (span 인자 필요)
│   │   ├── log_node_start/complete()  # 노드 로깅
│   │   └── calculate_cost()       # 비용 계산
│   │
│   └── strands_utils.py           # Strands 에이전트 OTEL 헬퍼
│       ├── observability_session()  # 세션 컨텍스트 매니저
│       ├── add_span_event()       # 스팬 이벤트 (현재 스팬)
│       ├── set_span_attributes()  # 스팬 속성 (현재 스팬)
│       ├── record_exception()     # 예외 기록 (현재 스팬)
│       └── TokenTracker           # 토큰 사용량 추적
├── docs/
│   └── observability.md           # 이 문서
└── test_workflow.py               # 워크플로우 실행
```

## 관련 파일

| 파일 | 역할 |
|------|------|
| `config/observability.env` | OTEL 환경 변수 (복사해서 `source`로 로드) |
| `src/utils/observability.py` | 핵심 OTEL 유틸리티 (trace_agent, trace_workflow 등) |
| `src/utils/strands_utils.py` | Strands 에이전트용 OTEL 헬퍼 (observability_session 등) |
| `src/graph/nodes.py` | 파이프라인 노드 (OTEL 스팬 자동 생성) |
| `test_workflow.py` | 워크플로우 실행 진입점 |

---

## 참고 자료

- [AWS ADOT Collector-less 가이드](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLP-UsingADOT.html)
- [AWS X-Ray OTLP 엔드포인트](https://docs.aws.amazon.com/xray/latest/devguide/xray-opentelemetry.html)
- [Strands Agents Observability](https://strandsagents.com/latest/documentation/docs/user-guide/observability/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
