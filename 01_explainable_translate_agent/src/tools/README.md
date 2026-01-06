# Tools - 번역 에이전트 도구

Strands Agent 기반 번역 파이프라인 도구입니다.

## Agent-as-Tool 패턴

| 특성 | 효과 |
|------|------|
| **Python이 오케스트레이션** | 워크플로우 흐름을 코드로 명시적 제어 |
| **각 Tool = 전문 에이전트** | 번역/평가 각각 독립된 프롬프트와 책임 |
| **병렬 실행** | `asyncio.gather`로 3개 평가 동시 실행 |
| **디버깅 용이** | 각 도구 출력을 개별 검사 가능 |

---

## 파일 구조

```
src/tools/
├── translator_tool.py             # 번역 도구
├── backtranslator_tool.py         # 역번역 도구
├── accuracy_evaluator_tool.py     # 정확성 평가
├── compliance_evaluator_tool.py   # 규정 준수 평가
└── quality_evaluator_tool.py      # 품질 평가
```

---

## 도구 목록

| 도구 | 역할 | 주요 입력 |
|------|------|----------|
| `translate` | 고품질 번역 생성 | Glossary, Feedback |
| `backtranslate` | 역번역 (의미 보존 검증용) | Translation |
| `evaluate_accuracy` | 정확성 평가 | Glossary, Backtranslation |
| `evaluate_compliance` | 규정 준수 평가 | Risk Profile |
| `evaluate_quality` | 품질 평가 | Glossary (충돌 방지) |

### 3개 평가 에이전트

| 에이전트 | 평가 항목 | 점수 기준 |
|----------|-----------|-----------|
| **Accuracy** | 의미 보존, 용어집 준수, 역번역 비교 | 5: 완벽 일치, 3-4: 경미한 차이, ≤2: 의미 왜곡 |
| **Compliance** | 금칙어, 면책조항, 개인정보 규칙 | 5: 규정 준수, 3-4: 경미한 위반, ≤2: 심각한 위반 |
| **Quality** | 유창성, 톤/격식, 문화적 적합성 | 5: 원어민 수준, 3-4: 어색함, ≤2: 부자연스러움 |

---

## 사용 예시

### 번역

```python
from src.tools import translate

result = await translate(
    source_text="ABC 클라우드에서 데이터를 백업하세요.",
    source_lang="ko",
    target_lang="en-rUS",
    glossary={"ABC 클라우드": "ABC Cloud"}
)
print(result.translation)  # "Back up your data on ABC Cloud."
```

### 역번역

```python
from src.tools import backtranslate

result = await backtranslate(
    translation="Back up your data on ABC Cloud.",
    source_lang="ko",
    target_lang="en-rUS"
)
print(result.backtranslation)  # "ABC 클라우드에서 데이터를 백업하세요."
```

### 병렬 평가

```python
from src.tools import evaluate_accuracy, evaluate_compliance, evaluate_quality
import asyncio

accuracy, compliance, quality = await asyncio.gather(
    evaluate_accuracy(source, translation, backtranslation, glossary=glossary),
    evaluate_compliance(source, translation, risk_profile=profile),
    evaluate_quality(source, translation, glossary=glossary)
)

# 점수 집계
scores = {
    "accuracy": accuracy.score,
    "compliance": compliance.score,
    "quality": quality.score
}
min_score = min(scores.values())
```

### 피드백 기반 재번역 (Maker-Checker)

```python
from src.tools import translate

# 첫 번역
result = await translate(source_text, "ko", "en-rUS", glossary=glossary)

# 평가 후 피드백 반영하여 재번역
if needs_revision:
    result = await translate(
        source_text, "ko", "en-rUS",
        glossary=glossary,
        feedback="용어집의 'ABC Cloud' 대신 'ABC Company cloud'로 잘못 번역됨. 수정 필요."
    )
```

### Glossary-Aware Quality

Quality 에이전트가 용어집 제약을 인식하여 Accuracy와 충돌 방지:

```python
# Quality 에이전트에 Glossary 전달
quality_result = await evaluate_quality(
    source_text=source,
    translation=translation,
    glossary={"고객센터": "Customer Support"},  # 용어집 전달
    content_type="FAQ"
)

# "Customer Support"가 어색해도 용어집에 있으면 감점 안함
```

### Risk Profile 기반 Compliance

```python
from src.utils import get_risk_profile

# 국가별 규제 프로파일 로드
profile = get_risk_profile("US")

# Compliance 평가 시 프로파일 적용
compliance_result = await evaluate_compliance(
    source_text=source,
    translation=translation,
    risk_profile=profile  # US 규제 적용 (FTC, CCPA 등)
)
```

---

## 응답 구조

### TranslationResult (번역)

```python
TranslationResult(
    translation="Back up your data on ABC Cloud.",
    candidates=["Back up your data on ABC Cloud."],
    reasoning_chain=["용어집 적용: ABC 클라우드 → ABC Cloud"],
    latency_ms=1500,
    token_usage={"input_tokens": 450, "output_tokens": 89}
)
```

### BacktranslationResult (역번역)

```python
BacktranslationResult(
    backtranslation="ABC 클라우드에서 데이터를 백업하세요.",
    latency_ms=892,
    token_usage={"input_tokens": 120, "output_tokens": 45}
)
```

### AgentResult (평가)

```python
AgentResult(
    agent_name="accuracy",           # accuracy, compliance, quality
    score=5,                         # 0-5 점수
    verdict="pass",                  # pass, review, fail
    reasoning_chain=[                # CoT 추론 과정
        "의미 보존 확인 - 원문 의미 유지됨",
        "용어집 검증 - 'ABC Cloud' 올바르게 사용",
        "역번역 비교 - 유사도 95%"
    ],
    issues=[],                       # 발견된 문제
    corrections=[],                  # 수정 제안
    latency_ms=1200,
    token_usage={"input_tokens": 500, "output_tokens": 150}
)
```

### Correction (수정 제안)

```python
Correction(
    original="ABC Company cloud",
    suggested="ABC Cloud",
    reason="용어집에 따라 'ABC Cloud' 사용 필요"
)
```

---

## 프롬프트 캐싱

System Prompt는 캐싱되어 90% 비용 절감:

```python
# System prompt - 캐싱됨 (src/prompts/*.md에서 로드)
system_prompt = load_prompt("translator", source_lang="ko", target_lang="en-rUS")

# User message - 동적 (매 요청마다 변경)
user_message = f"""
<source_text>
{source_text}
</source_text>
"""
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/prompts/*.md` | 시스템 프롬프트 템플릿 |
| `src/models/agent_result.py` | AgentResult, Correction 모델 |
| `src/models/translation_result.py` | TranslationResult 모델 |
| `data/glossaries/` | 도메인별 용어집 |
| `data/risk_profiles/` | 국가별 규제 프로파일 |
| `config/models.yaml` | 모델 설정 (temperature, max_tokens) |
