# 설정 (Config)

번역 에이전트 워크플로우의 모든 설정 파일을 관리합니다.

## 파일 구조

```
config/
├── README.md              # 이 문서
├── languages.yaml         # 지원 언어 목록 (45개)
├── models.yaml            # AWS Bedrock 모델 설정
├── thresholds.yaml        # 점수 임계값 및 판정 기준
└── risk_profiles/         # 국가별 리스크 프로파일
    ├── README.md
    ├── US.yaml
    └── DEFAULT.yaml
```

## 파일별 설명

---

### languages.yaml

45개 언어 (소스 1개 + 타겟 44개)를 정의합니다.

#### 목적

번역 파이프라인에서 지원하는 모든 언어와 해당 언어의 특성(격식 수준, 텍스트 방향, 커버 지역)을 정의합니다.

#### 스키마

```yaml
languages:
  - code: en              # 언어 코드
    name: English         # 언어 이름
    locale: en-US         # 로케일
    formality: medium     # 격식 수준 (low | medium | high)
    direction: ltr        # 텍스트 방향 (ltr | rtl)
    regions:              # 커버 국가/지역
      - United States
      - United Kingdom

source:
  code: ko
  name: Korean
  locale: ko-KR
  formality: high
  direction: ltr
```

#### 전체 언어 목록 (45개)

| # | 코드 | 언어 | 격식 | 방향 | 주요 지역 |
|---|------|------|------|------|-----------|
| 1 | `en` | English | medium | ltr | US, Africa, Asia-Pacific, Americas, Middle East, Europe |
| 2 | `en-rGB` | English (UK) | medium | ltr | United Kingdom |
| 3 | `fr` | French | high | ltr | France, Belgium, Canada, Africa |
| 4 | `pt` | Portuguese | high | ltr | Portugal, Brazil, Angola, Mozambique |
| 5 | `ar` | Arabic | high | **rtl** | Saudi Arabia, UAE, Egypt, Middle East |
| 6 | `es` | Spanish | high | ltr | Spain, Latin America |
| 7 | `zh-CN` | Chinese (Simplified) | medium | ltr | China, Singapore |
| 8 | `zh-HK` | Chinese (Hong Kong) | medium | ltr | Hong Kong, Macao |
| 9 | `zh-TW` | Chinese (Traditional) | medium | ltr | Taiwan |
| 10 | `id` | Indonesian | medium | ltr | Indonesia |
| 11 | `ja` | Japanese | high | ltr | Japan |
| 12 | `ko` | **Korean (소스)** | high | ltr | Korea |
| 13 | `ms` | Malay | medium | ltr | Malaysia |
| 14 | `vi` | Vietnamese | high | ltr | Vietnam |
| 15 | `th` | Thai | high | ltr | Thailand |
| 16 | `fa` | Persian | high | **rtl** | Iran |
| 17 | `he` | Hebrew | medium | **rtl** | Israel |
| 18 | `ur` | Urdu | high | **rtl** | Pakistan |
| 19 | `de` | German | high | ltr | Germany, Austria, Switzerland |
| 20 | `nl` | Dutch | medium | ltr | Netherlands, Belgium |
| 21 | `hr` | Croatian | high | ltr | Croatia, Bosnia and Herzegovina |
| 22 | `bg` | Bulgarian | high | ltr | Bulgaria |
| 23 | `el` | Greek | high | ltr | Greece, Cyprus |
| 24 | `cs` | Czech | high | ltr | Czech Republic |
| 25 | `da` | Danish | low | ltr | Denmark |
| 26 | `et` | Estonian | medium | ltr | Estonia |
| 27 | `fi` | Finnish | low | ltr | Finland |
| 28 | `mk` | Macedonian | high | ltr | North Macedonia |
| 29 | `hu` | Hungarian | high | ltr | Hungary |
| 30 | `ga` | Irish | medium | ltr | Ireland |
| 31 | `it` | Italian | high | ltr | Italy |
| 32 | `kk` | Kazakh | high | ltr | Kazakhstan |
| 33 | `lv` | Latvian | high | ltr | Latvia |
| 34 | `lt` | Lithuanian | high | ltr | Lithuania |
| 35 | `ro` | Romanian | high | ltr | Romania, Moldova |
| 36 | `ru` | Russian | high | ltr | Russia, Belarus, Kazakhstan |
| 37 | `sr` | Serbian | high | ltr | Serbia, Montenegro |
| 38 | `nb` | Norwegian | low | ltr | Norway |
| 39 | `pl` | Polish | high | ltr | Poland |
| 40 | `sk` | Slovak | high | ltr | Slovakia |
| 41 | `sl` | Slovenian | high | ltr | Slovenia |
| 42 | `sv` | Swedish | low | ltr | Sweden |
| 43 | `tr` | Turkish | high | ltr | Turkiye |
| 44 | `uk` | Ukrainian | high | ltr | Ukraine |
| 45 | `uz` | Uzbek | high | ltr | Uzbekistan |

#### 격식 수준 (Formality)

번역 시 사용할 경어/존칭 수준을 결정합니다.

| 수준 | 설명 | 적용 언어 예시 |
|------|------|----------------|
| `high` | 경어/존칭 필수 | 일본어 (Keigo), 독일어 (Sie), 프랑스어 (Vous), 스페인어 (Usted) |
| `medium` | 일반적 정중함 | 영어, 중국어, 네덜란드어 |
| `low` | 비격식 허용 | 스웨덴어 (Du reform), 덴마크어, 핀란드어, 노르웨이어 |

#### RTL 언어 (우→좌 텍스트 방향)

UI 레이아웃 및 텍스트 정렬에 영향:

- **Arabic (ar)** - 아랍어
- **Persian (fa)** - 페르시아어
- **Hebrew (he)** - 히브리어
- **Urdu (ur)** - 우르두어

#### 코드에서 사용법

```python
from src.utils import ConfigLoader

config = ConfigLoader()

# 전체 타겟 언어 목록
languages = config.get_languages()
print(f"타겟 언어: {len(languages)}개")

# 소스 언어
source = config.get_source_language()
print(f"소스: {source['name']} ({source['code']})")

# 특정 조건 필터링
rtl_languages = [l for l in languages if l.get('direction') == 'rtl']
high_formality = [l for l in languages if l.get('formality') == 'high']
```

---

### models.yaml

AWS Bedrock에서 사용할 Claude 모델을 역할별로 정의합니다.

#### 목적

번역 파이프라인의 각 단계에서 사용할 LLM 모델과 호출 설정을 정의합니다. 역할별로 최적화된 모델과 파라미터를 사용하여 품질과 비용의 균형을 맞춥니다.

#### 스키마

```yaml
region: us-west-2                    # AWS Bedrock 리전

# Model IDs Reference (High Quality Only: Opus 4.5, Sonnet 4.5)
# Opus 4.5:     global.anthropic.claude-opus-4-5-20251101-v1:0   (최고 품질)
# Sonnet 4.5:   global.anthropic.claude-sonnet-4-5-20250929-v1:0 (고품질)

models:
  translator:                        # 역할 이름
    model_id: "global.anthropic.claude-opus-4-5-20251101-v1:0"
    max_tokens: 2000                 # 최대 출력 토큰
    temperature: 0.3                 # 창의성 (0.0 = 결정적, 1.0 = 창의적)
    description: "Primary translation model"

retry:
  max_attempts: 3                    # 최대 재시도 횟수
  base_delay_seconds: 1              # 기본 대기 시간
  max_delay_seconds: 10              # 최대 대기 시간
  exponential_base: 2                # 지수 백오프 배수

token_limits:
  max_input_tokens: 100000           # 최대 입력 토큰
  max_output_tokens: 4096            # 최대 출력 토큰
  warning_threshold: 0.8             # 80% 도달 시 경고

caching:
  prompt_cache_enabled: true         # 프롬프트 캐싱
  cache_type: "default"              # default | ephemeral
```

#### 역할별 모델 구성

| 역할 | 모델 | Temp | 용도 |
|------|------|------|------|
| `translator` | Opus 4.5 | 0.1 | 메인 번역 (최고 품질) |
| `backtranslator` | Opus 4.5 | 0.0 | 역번역 검증 |
| `accuracy_evaluator` | Opus 4.5 | 0.0 | 정확성/용어집 평가 |
| `compliance_evaluator` | Opus 4.5 | 0.0 | 법률/안전 검사 |
| `quality_evaluator` | Opus 4.5 | 0.0 | 톤/문화 평가 (뉘앙스) |

> **High Quality Policy**: 모든 에이전트가 Opus 4.5 사용

#### Temperature 가이드

| 값 | 특성 | 적용 역할 |
|----|------|-----------|
| 0.1 | 결정적, 일관성 높음 | 평가 에이전트 (동일 입력 → 동일 점수) |
| 0.3 | 약간의 창의성 | 번역 (자연스러운 표현 선택) |
| 0.7+ | 창의적, 다양성 높음 | 사용 안함 (번역 품질에 부적합) |

#### 모델 선택 전략

```
┌─────────────────────────────────────────────────────────────────────┐
│              모델 선택 전략 (All Opus 4.5)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Opus 4.5 (최고 품질) - 모든 역할에 적용                            │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  - 번역 생성 (translator)                                    │   │
│   │  - 역번역 검증 (backtranslator)                              │   │
│   │  - 정확성/용어 평가 (accuracy_evaluator)                      │   │
│   │  - 법률/안전 검사 (compliance_evaluator)                     │   │
│   │  - 톤/문화 평가 (quality_evaluator)                          │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│   [ 5 Opus calls per translation unit ]                            │
└─────────────────────────────────────────────────────────────────────┘
```

#### 재시도 로직 (Exponential Backoff)

```
실패 시 재시도 대기 시간:
  1차 실패: 1초 대기 (base_delay)
  2차 실패: 2초 대기 (1 × 2^1)
  3차 실패: 4초 대기 (1 × 2^2) - 단, max 10초 제한
```

#### 코드에서 사용법

```python
from src.utils import get_bedrock_client, BedrockClient

# 싱글톤 클라이언트 (권장)
client = get_bedrock_client()

# 역할별 모델로 호출
messages = [{"role": "user", "content": [{"text": "번역: 안녕하세요"}]}]
response = client.converse(
    role="translator",              # models.yaml에 정의된 역할
    messages=messages,
    system_prompt="당신은 전문 번역가입니다."
)

# 텍스트 + 토큰 사용량 추출
text, usage = client.converse_and_extract(role="translator", messages=messages)
print(f"응답: {text}")
print(f"토큰: 입력 {usage['input_tokens']}, 출력 {usage['output_tokens']}")
```

#### 비용 최적화 팁

1. **프롬프트 캐싱 활성화**: 동일 시스템 프롬프트 재사용 시 비용 절감
2. **max_tokens 적절히 설정**: 불필요하게 높으면 비용 증가
3. **배치 처리**: 여러 FAQ를 묶어서 처리하여 오버헤드 감소

---

### thresholds.yaml

점수 체계, 판정 기준, 가드레일, HITL 설정을 정의합니다.

#### 목적

번역 품질 평가의 모든 수치적 기준을 중앙 관리합니다. 에이전트 점수 해석, 자동/수동 판정 분기, 시스템 보호를 위한 임계값을 정의합니다.

#### 스키마

```yaml
scoring:
  min_score: 0           # 최소 점수
  max_score: 5           # 최대 점수
  scale_description: ... # 점수별 의미

decision:
  pass_threshold: 5      # 모든 에이전트 5점이면 Pass
  fail_threshold: 2      # 이하면 Fail
  borderline_scores: [3, 4]  # 재생성 → 최대 횟수 초과 시 Rejected

regeneration:
  max_attempts: 1        # 최대 재생성 횟수
  include_feedback: true # 이전 피드백 포함

agent_agreement:
  disagreement_threshold: 3   # 에이전트 간 점수 차이 임계값
  min_agreement_score: 0.6    # 최소 일치도

hitl:
  timeout_seconds: 300        # PM 검토 대기 시간
  poll_interval_seconds: 3    # S3 폴링 주기
  s3_bucket: "..."            # 검토 요청 버킷
  s3_prefix: "reviews/"       # S3 경로 프리픽스

guardrails:
  input:
    max_source_length: 5000   # 입력 최대 길이
    min_source_length: 1      # 입력 최소 길이
  runtime:
    max_latency_ms: 60000     # 에이전트당 최대 지연
    max_total_latency_ms: 300000
    max_retries: 3
  output:
    require_all_agents_pass: true
    min_avg_score: 3.5

metrics:
  track: [...]                # 추적할 메트릭 목록
  alerts:
    block_rate_threshold: 0.2 # 차단율 경고 기준
    hitl_rate_threshold: 0.3  # HITL 비율 경고 기준
```

#### 점수 스케일 (0-5)

LLM-as-Judge의 일관성을 위해 저정밀 스케일(0-5)을 사용합니다.

| 점수 | 등급 | 설명 | 액션 |
|------|------|------|------|
| **5** | Perfect | 문제 없음 | 자동 발행 |
| **4** | Minor | 경미한 문제 | 재생성 (피드백 반영) |
| **3** | Borderline | 경계, 판단 어려움 | 재생성 (피드백 반영) |
| **2** | Significant | 심각한 문제 | 즉시 차단 |
| **1** | Severe | 매우 심각, 대폭 수정 필요 | 즉시 차단 |
| **0** | Unusable | 완전 실패 | 즉시 차단 |

> **참고**: 재생성 최대 횟수 초과 시 REJECTED로 처리 (HITL 미구현)

#### 판정 흐름도

```
                    ┌──────────────────┐
                    │   평가 점수      │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         = 5점          3-4점          ≤ 2점
              │              │              │
              ▼              ▼              ▼
       ┌──────────┐   ┌───────────┐   ┌──────────┐
       │   PASS   │   │ REGENERATE│   │  BLOCK   │
       │ 자동 발행 │   │           │   │ 즉시 차단 │
       └──────────┘   └─────┬─────┘   └──────────┘
                            │
                            ▼
                  ┌─────────────────┐
                  │ 재생성 시도      │
                  │ (max_attempts회) │
                  └────────┬────────┘
                           │
              ┌────────────┴────────────┐
              │ 모든 점수 5              │ 아직 < 5
              ▼                          ▼
        ┌──────────┐              ┌──────────┐
        │   PASS   │              │ REJECTED │
        │ 자동 발행 │              │ 거부     │
        └──────────┘              └──────────┘
```

#### 에이전트 합의 (Agent Agreement)

3개 평가 에이전트 간 점수 차이가 `disagreement_threshold` (3) 이상이면 불일치로 REJECTED:

| 에이전트 | Accuracy | Compliance | Quality | 최대 차이 | 결과 |
|----------|----------|------------|---------|-----------|------|
| 점수 예1 | 5 | 5 | 4 | 1 | **정상** (차이 < 3) |
| 점수 예2 | 5 | 5 | 3 | 2 | **정상** (차이 < 3) |
| 점수 예3 | 5 | 2 | 4 | 3 | **REJECTED** (차이 ≥ 3, 불일치) |

#### 가드레일 (Guardrails)

시스템 보호를 위한 3단계 검증:

| 단계 | 검증 항목 | 임계값 | 초과 시 |
|------|-----------|--------|---------|
| **Input** | 원문 길이 | 1-5000자 | 요청 거부 |
| **Runtime** | 에이전트 지연 | 60초 | 타임아웃 |
| **Runtime** | 전체 워크플로우 | 5분 | 타임아웃 |
| **Output** | 모든 에이전트 Pass | 전부 =5점 | 5점 미만 시 재생성 |
| **Output** | 평균 점수 | ≥3.5점 | 경고 |

#### HITL (Human-in-the-Loop)

> **⚠️ 현재 미구현**: HITL 에스컬레이션 대신 REJECTED로 처리됩니다.

PM 검토가 필요한 경우 S3를 통해 비동기 협업 (향후 구현 예정):

```
┌─────────┐         ┌─────────┐         ┌─────────┐
│ 에이전트 │──요청──▶│   S3    │◀──응답──│   PM    │
│         │◀──결과──│ Bucket  │         │ Console │
└─────────┘         └─────────┘         └─────────┘
     │                                       │
     │◀───── poll_interval (3초) ─────▶│
     │◀───── timeout (300초) ───────────▶│
```

#### 메트릭 및 알림

실시간 모니터링을 위한 메트릭:

| 메트릭 | 설명 | 알림 임계값 |
|--------|------|-------------|
| `block_rate` | 차단된 번역 비율 | > 20% |
| `hitl_escalation_rate` | HITL 에스컬레이션 비율 | > 30% |
| `avg_latency` | 평균 처리 시간 | > 30초 |
| `agent_scores` | 에이전트별 점수 분포 | - |
| `agent_agreement` | 에이전트 간 일치도 | - |

#### 코드에서 사용법

```python
from src.utils import get_thresholds

thresholds = get_thresholds()

# 판정 로직
score = 4
if score >= thresholds["decision"]["pass_threshold"]:
    result = "PASS"
elif score <= thresholds["decision"]["fail_threshold"]:
    result = "FAIL"
else:
    result = "BORDERLINE"

# 가드레일 검증
source_text = "번역할 텍스트"
max_len = thresholds["guardrails"]["input"]["max_source_length"]
if len(source_text) > max_len:
    raise ValueError(f"입력이 {max_len}자를 초과합니다")

# 에이전트 합의 검증
scores = {"accuracy": 5, "compliance": 3, "quality": 4}
max_diff = max(scores.values()) - min(scores.values())
if max_diff >= thresholds["agent_agreement"]["disagreement_threshold"]:
    escalate_to_hitl()
```

#### 튜닝 가이드

| 상황 | 조정 방향 |
|------|-----------|
| 차단율이 너무 높음 | `fail_threshold` 1로 하향 |
| 품질 문제 증가 | `pass_threshold` 5로 상향 |
| HITL 과부하 | `disagreement_threshold` 3으로 상향 |
| 타임아웃 빈발 | `max_latency_ms` 증가 |

## 코드에서 사용법

```python
from src.utils import get_config, get_thresholds, ConfigLoader

# 단일 설정 파일 로드
languages = get_config("languages")
models = get_config("models")
thresholds = get_thresholds()

# ConfigLoader로 여러 설정 접근
config = ConfigLoader()
languages = config.get_languages()
source = config.get_source_language()
model_cfg = config.get_model_config("translator")
```

## 설정 변경 시 주의사항

1. **YAML 문법 검증**: 변경 후 반드시 파싱 테스트
2. **버전 관리**: 중요한 변경은 Git 커밋으로 추적
3. **영향 범위 확인**: 임계값 변경은 전체 판정 로직에 영향
4. **테스트**: 설정 변경 후 통합 테스트 수행
