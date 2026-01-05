# Tools - 번역 에이전트 도구 모음

Strands Agent 기반 번역 파이프라인 도구들입니다.

## 왜 Agent-as-Tool 패턴인가?

| 접근법 | 문제점 |
|--------|--------|
| 단일 LLM | 모든 작업 혼합 → 품질 저하, 디버깅 어려움 |
| 멀티 에이전트 (자율) | 에이전트 간 통신 복잡, 제어 어려움 |

**Agent-as-Tool 해결책:**

| 특성 | 효과 |
|------|------|
| **Python이 오케스트레이션** | 워크플로우 흐름을 코드로 명시적 제어 |
| **각 Tool = 전문 에이전트** | 번역/평가 각각 독립된 프롬프트와 책임 |
| **병렬 실행 용이** | `asyncio.gather`로 3개 평가 동시 실행 |
| **디버깅 용이** | 각 도구 출력을 개별 검사 가능 |

---

## 아키텍처

```
              ┌──────────┐          ┌──────────────┐
              │ GLOSSARY │          │ RISK PROFILE │
              └────┬─────┘          └──────┬───────┘
                   │                       │
┌──────────────────┼───────────────────────┼──────────────────────┐
│                  │  Programmatic Orchestration                  │
│                  │  (Python controls workflow)                  │
└──────────────────┼───────────────────────┼──────────────────────┘
                   │                       │
        ┌──────────┴──────────┬────────────┴──────────┐
        ▼                     ▼                       ▼
┌───────────────┐     ┌───────────────┐       ┌───────────────┐
│   Translator  │     │ Backtranslator│       │   Evaluators  │
│   (Opus 4.5)  │     │  (Opus 4.5)   │       │  (Opus 4.5)   │
│               │     │               │       │  × 3 (병렬)   │
│  ← Glossary   │     │               │       │ ← Risk Profile│
└───────────────┘     └───────────────┘       └───────────────┘
```

---

## 도구 목록

| 도구 | 모델 | 역할 | 입력 |
|------|------|------|------|
| `translator_tool.py` | Claude Opus 4.5 | 고품질 번역 생성 | Glossary, Feedback |
| `backtranslator_tool.py` | Claude Opus 4.5 | 역번역 (의미 보존 검증용) | - |
| `accuracy_evaluator_tool.py` | Claude Opus 4.5 | 정확성 평가 | Glossary, Backtranslation |
| `compliance_evaluator_tool.py` | Claude Opus 4.5 | 규정 준수 평가 | Risk Profile |
| `quality_evaluator_tool.py` | Claude Opus 4.5 | 품질 평가 (원어민 수준) | Glossary (충돌 방지) |

### 3개 평가 에이전트 상세

| 에이전트 | 평가 항목 | 점수 기준 |
|----------|-----------|-----------|
| **Accuracy** | 의미 보존, 용어집 준수, 역번역 비교 | 5: 완벽 일치, 3-4: 경미한 차이, ≤2: 의미 왜곡 |
| **Compliance** | 금칙어, 면책조항, 개인정보 규칙 | 5: 규정 준수, 3-4: 경미한 위반, ≤2: 심각한 위반 |
| **Quality** | 유창성, 톤/격식, 문화적 적합성 | 5: 원어민 수준, 3-4: 어색함, ≤2: 부자연스러움 |

## 설계 원칙

### 1. Async-Only API
모든 도구는 비동기 함수만 제공합니다:
```python
# Good - async only
result = await translate(source_text, "ko", "en-rUS")

# 병렬 실행
results = await asyncio.gather(
    evaluate_accuracy(...),
    evaluate_compliance(...),
    evaluate_quality(...)
)
```

### 2. 프롬프트 캐싱 분리
- **System Prompt**: 정적 콘텐츠 (캐싱됨, 90% 비용 절감)
- **User Message**: 동적 콘텐츠 (매 요청마다 변경)

```python
# System prompt - 캐싱됨 (src/prompts/*.md)
system_prompt = load_prompt("translator", source_lang="ko", target_lang="en-rUS")

# User message - 동적 (textwrap.dedent 사용)
user_message = dedent(f"""\
    <source_text>
    {source_text}
    </source_text>
    ...
""")
```

### 3. textwrap.dedent 패턴
모든 사용자 메시지는 `dedent`로 가독성 향상:
```python
from textwrap import dedent

def _build_user_message(...) -> str:
    return dedent(f"""\
        다음 번역을 평가하세요.

        <source_text>
        {source_text}
        </source_text>
        ...
    """)
```

### 4. 일관된 응답 구조
모든 평가 도구는 `AgentResult` 반환:
```python
@dataclass
class AgentResult:
    agent_name: str           # "accuracy", "compliance", "quality"
    reasoning_chain: List[str] # 추론 과정
    score: int                # 0-5
    verdict: str              # "pass", "review", "fail"
    issues: List[str]         # 발견된 문제
    corrections: List[Correction]  # 수정 제안
    token_usage: Dict         # 토큰 사용량
    latency_ms: int           # 응답 시간
```

## 사용 예시

### 단일 번역
```python
from src.tools import translate

result = await translate(
    source_text="ABC 클라우드에서 데이터를 백업하세요.",
    source_lang="ko",
    target_lang="en-rUS",
    glossary={"ABC 클라우드": "ABC Cloud"}
)
print(result.translation)
```

### 병렬 평가
```python
from src.tools import (
    evaluate_accuracy,
    evaluate_compliance,
    evaluate_quality
)

accuracy, compliance, quality = await asyncio.gather(
    evaluate_accuracy(source, translation, backtranslation, glossary=glossary),
    evaluate_compliance(source, translation, risk_profile=profile),
    evaluate_quality(source, translation, content_type="FAQ")
)

# 점수 집계
min_score = min(accuracy.score, compliance.score, quality.score)
```

### Maker-Checker 루프
```python
from src.tools import translate

# 첫 번역
result = await translate(source_text, "ko", "en-rUS")

# 피드백 기반 재번역
if needs_revision:
    result = await translate(
        source_text, "ko", "en-rUS",
        feedback="용어집의 'ABC Cloud' 대신 'ABC Company cloud'로 잘못 번역됨. 수정 필요."
    )
```

### Glossary-Aware Quality (에이전트 간 충돌 방지)

Quality 에이전트가 용어집 제약을 인식하여 충돌을 방지합니다:

```python
# Quality 에이전트에 Glossary 전달
quality_result = await evaluate_quality(
    source_text=source,
    translation=translation,
    glossary={"고객센터": "Customer Support"},  # 용어집 전달
    content_type="FAQ"
)

# Quality 에이전트는 "Customer Support"가 어색해도
# 용어집에 있으면 감점하지 않음
```

### Risk Profile 기반 Compliance 평가

```python
from src.utils import get_risk_profile

# 국가별 규제 프로파일 로드
profile = get_risk_profile("US")

# Compliance 평가 시 프로파일 적용
compliance_result = await evaluate_compliance(
    source_text=source,
    translation=translation,
    risk_profile=profile  # US 규제 적용 (FTC, CCPA, COPPA 등)
)

# profile에 따라 금칙어, 면책조항, 개인정보 규칙 검사
```

## 파일 구조

```
src/tools/
├── __init__.py                    # 공개 API 내보내기
├── translator_tool.py             # 번역 도구
├── backtranslator_tool.py         # 역번역 도구
├── accuracy_evaluator_tool.py     # 정확성 평가
├── compliance_evaluator_tool.py   # 규정 준수 평가
├── quality_evaluator_tool.py      # 품질 평가
└── README.md                      # 이 문서
```

## 토큰 사용량 및 비용 추적

모든 도구는 `token_usage`와 `latency_ms`를 반환합니다:

```python
result = await evaluate_accuracy(...)

print(f"입력 토큰: {result.token_usage['input_tokens']}")
print(f"출력 토큰: {result.token_usage['output_tokens']}")
print(f"응답 시간: {result.latency_ms}ms")

# 비용 계산 (Claude Opus 4.5 기준)
input_cost = result.token_usage['input_tokens'] * 0.015 / 1000
output_cost = result.token_usage['output_tokens'] * 0.075 / 1000
total_cost = input_cost + output_cost
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/prompts/*.md` | 시스템 프롬프트 템플릿 |
| `src/utils/strands_utils.py` | Strands Agent 유틸리티 |
| `src/models/` | 데이터 모델 정의 |
| `data/risk_profiles/` | 국가별 규제 프로파일 |
| `data/glossaries/` | 도메인별 용어집 |
