# Tools - 번역 에이전트 도구 모음

Strands Agent 기반 번역 파이프라인 도구들입니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    Programmatic Orchestration                    │
│                    (Python controls workflow)                    │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│   Translator  │       │ Backtranslator│       │   Evaluators  │
│   (Opus 4.5)  │       │  (Opus 4.5)   │       │  (Opus 4.5)   │
└───────────────┘       └───────────────┘       └───────────────┘
```

## 도구 목록

| 도구 | 모델 | 역할 |
|------|------|------|
| `translator_tool.py` | Claude Opus 4.5 | 고품질 번역 생성 |
| `backtranslator_tool.py` | Claude Opus 4.5 | 역번역 (검증용) |
| `accuracy_evaluator_tool.py` | Claude Opus 4.5 | 정확성 평가 |
| `compliance_evaluator_tool.py` | Claude Opus 4.5 | 규정 준수 평가 |
| `quality_evaluator_tool.py` | Claude Opus 4.5 | 품질 평가 (원어민 수준) |

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

## 관련 파일

- `src/prompts/*.md` - 시스템 프롬프트 템플릿
- `src/utils/strands_utils.py` - Strands Agent 유틸리티
- `src/models/` - 데이터 모델 정의
