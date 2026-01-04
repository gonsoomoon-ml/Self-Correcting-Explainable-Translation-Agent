# SOPs (Standard Operating Procedures)

> 의사결정 로직 레이어 - 번역 파이프라인의 판정 및 흐름 제어

---

## 개요

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SOP 흐름도                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   [3개 평가 에이전트]                                                     │
│         │                                                               │
│         ▼                                                               │
│   ┌─────────────────┐                                                   │
│   │ EvaluationGate  │ ◄─── 점수 기반 판정                                │
│   │     SOP         │                                                   │
│   └────────┬────────┘                                                   │
│            │                                                            │
│   ┌────────┼────────┬────────────┐                                      │
│   │        │        │            │                                      │
│   ▼        ▼        ▼            ▼                                      │
│ ┌────┐  ┌─────┐  ┌──────┐  ┌──────────┐                                │
│ │PASS│  │BLOCK│  │REGEN │  │ REJECTED │                                │
│ └────┘  └─────┘  └──┬───┘  └──────────┘                                │
│                     │                                                   │
│                     ▼                                                   │
│               ┌───────────┐                                             │
│               │Regeneration│                                            │
│               │    SOP     │                                            │
│               └───────────┘                                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## SOPs vs Skills vs Tools

| 구분 | 역할 | 형태 | 예시 |
|------|------|------|------|
| **Skill** | 지식/능력 정의 | Markdown (SKILL.md) | 번역 가이드라인 |
| **SOP** | 의사결정 절차 | Python 클래스 | 점수 판정 로직 |
| **Tool** | 실행 래퍼 | Python 함수 | 에이전트 호출 |

**SOPs의 특징:**
- 비즈니스 규칙을 코드로 구현
- 테스트 가능한 순수 로직
- LLM 호출 없이 결정 수행

---

## 파일 구조

```
sops/
├── __init__.py           # 모듈 exports
├── README.md             # 이 문서
├── evaluation_gate.py    # 평가 게이트 (핵심 판정)
└── regeneration.py       # 재생성 피드백 수집
```

---

## 1. evaluation_gate.py

> **Release Guard** - 번역 발행 가능 여부 최종 판정

### 역할

3개 평가 에이전트(Accuracy, Compliance, Quality)의 점수를 분석하여
번역을 발행할지, 재생성할지, 차단할지 결정합니다.

### 판정 규칙

```
┌─────────────────────────────────────────────────────────────┐
│                    판정 의사결정 트리                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   모든 에이전트 점수 = 5?                                     │
│         │                                                   │
│    ┌────┴────┐                                              │
│   YES       NO                                              │
│    │         │                                              │
│    ▼         ▼                                              │
│  PASS    어떤 에이전트 점수 ≤ 2?                              │
│    │              │                                         │
│    │         ┌────┴────┐                                    │
│    │        YES       NO                                    │
│    │         │         │                                    │
│    │         ▼         ▼                                    │
│    │      BLOCK    에이전트 간 점수 차이 ≥ 3?                 │
│    │         │              │                               │
│    │         │         ┌────┴────┐                          │
│    │         │        YES       NO                          │
│    │         │         │         │                          │
│    │         │         ▼         ▼                          │
│    │         │     REJECTED   재시도 가능?                   │
│    │         │    (불일치)          │                       │
│    │         │         │         ┌────┴────┐                │
│    │         │         │        YES       NO                │
│    │         │         │         │         │                │
│    │         │         │         ▼         ▼                │
│    │         │         │     REGENERATE  REJECTED           │
│    │         │         │         │         │                │
│    └─────────┴─────────┴─────────┴─────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 주요 클래스

```python
class EvaluationGateConfig:
    pass_threshold: int = 5       # 통과 최소 점수 (모든 에이전트 5점 필요)
    fail_threshold: int = 2       # 차단 최대 점수
    max_regenerations: int = 1    # 최대 재시도 횟수
    disagreement_threshold: int = 3  # 에이전트 불일치 임계값

class EvaluationGateSOP:
    def decide(
        agent_results: List[AgentResult],
        attempt_count: int = 1
    ) -> GateDecision
```

### 출력: GateDecision

| 필드 | 타입 | 설명 |
|------|------|------|
| `verdict` | Verdict | PASS / BLOCK / REGENERATE / REJECTED |
| `can_publish` | bool | 발행 가능 여부 |
| `scores` | Dict[str, int] | 에이전트별 점수 |
| `reasoning_chains` | Dict | 에이전트별 평가 과정 |
| `corrections` | List[dict] | 수정 제안 목록 |
| `agent_agreement_score` | float | 에이전트 간 일치도 (0-1) |

---

## 2. regeneration.py

> **Maker-Checker Loop** - 재생성을 위한 피드백 수집

### 역할

경계 점수(score 3-4) 발생 시 이전 평가의 문제점을 수집하여
번역 에이전트가 개선된 번역을 생성할 수 있도록 피드백을 포맷합니다.

### Maker-Checker 패턴

```
┌─────────────┐                      ┌─────────────┐
│   MAKER     │                      │   CHECKER   │
│ (Translator)│                      │(3 Evaluators)│
└──────┬──────┘                      └──────┬──────┘
       │                                    │
       │  1. 번역 생성                       │
       ├────────────────────────────────────▶
       │                                    │
       │                     2. 평가 + 피드백│
       ◀────────────────────────────────────┤
       │                                    │
       │  3. 피드백 반영 재생성               │
       ├────────────────────────────────────▶
       │                                    │
```

### 주요 클래스

```python
@dataclass
class RegenerationFeedback:
    previous_issues: List[str]      # 이전 문제점
    corrections: List[Correction]   # 수정 제안
    agent_feedbacks: Dict[str, List[str]]  # 에이전트별 분석
    triggering_agents: List[str]    # 재생성 유발 에이전트
    previous_translation: Optional[str]    # 이전 번역

class RegenerationSOP:
    def collect_feedback(
        agent_results: List[AgentResult]
    ) -> RegenerationFeedback

    def format_feedback_for_prompt(
        feedback: RegenerationFeedback,
        language: str = "ko"
    ) -> str
```

### 출력 예시 (프롬프트 주입용)

```xml
<previous_feedback>
이전 번역에서 다음 문제가 발견되었습니다:

**발견된 문제:**
1. 용어집 미적용: "ABC Cloud" → "ABC 클라우드"로 번역됨
2. 뉘앙스 손실: "반드시"의 강조가 약화됨

**수정 제안:**
- 'ABC 클라우드' → 'ABC Cloud'
  사유: 브랜드명은 번역하지 않음

위 문제점을 피하여 새로운 번역을 생성하세요.
</previous_feedback>
```

---

## 사용 예시

```python
from sops import EvaluationGateSOP, RegenerationSOP

# 1. 평가 결과로 판정
gate_sop = EvaluationGateSOP()
decision = gate_sop.decide(agent_results, attempt_count=1)

# 2. 판정에 따른 분기
if decision.verdict == Verdict.PASS:
    # 발행 가능
    publish(unit, translation)

elif decision.verdict == Verdict.REGENERATE:
    # 피드백 수집 후 재생성
    regen_sop = RegenerationSOP()
    feedback = regen_sop.collect_feedback(agent_results)
    prompt_addition = regen_sop.format_feedback_for_prompt(feedback)
    # → 번역 에이전트에 prompt_addition 주입하여 재생성

elif decision.verdict in (Verdict.BLOCK, Verdict.REJECTED):
    # 거부
    logger.error(f"Translation rejected: {decision.message}")
```

---

## 테스트

```bash
# SOP 기본 테스트
uv run python -c "
import sys
sys.path.insert(0, '/path/to/01_explainable_translate_agent')

from sops import EvaluationGateSOP
from src.models.agent_result import AgentResult

gate = EvaluationGateSOP()

# 모두 통과 (모든 점수 5)
results = [
    AgentResult(agent_name='accuracy', score=5, verdict='pass', reasoning_chain=[]),
    AgentResult(agent_name='compliance', score=5, verdict='pass', reasoning_chain=[]),
    AgentResult(agent_name='quality', score=5, verdict='pass', reasoning_chain=[]),
]
decision = gate.decide(results)
print(f'Verdict: {decision.verdict.value}')  # pass
print(f'Can publish: {decision.can_publish}')  # True

# 재생성 필요 (5,5,4 → 하나라도 5 미만)
results = [
    AgentResult(agent_name='accuracy', score=5, verdict='pass', reasoning_chain=[]),
    AgentResult(agent_name='compliance', score=5, verdict='pass', reasoning_chain=[]),
    AgentResult(agent_name='quality', score=4, verdict='regenerate', reasoning_chain=[]),
]
decision = gate.decide(results)
print(f'Verdict: {decision.verdict.value}')  # regenerate
"
```

---

## 설정 커스터마이징

```python
from sops import EvaluationGateSOP, EvaluationGateConfig

# 기본 설정 (현재 적용)
default_config = EvaluationGateConfig(
    pass_threshold=5,      # 모든 에이전트 5점 필요
    fail_threshold=2,      # 2점 이하 즉시 차단
    max_regenerations=1,   # 최대 1회 재시도
    disagreement_threshold=3  # 3점 차이 불일치로 간주
)

# 커스텀 설정 예시 (더 관대한 기준)
lenient_config = EvaluationGateConfig(
    pass_threshold=4,      # 4점 이상 통과
    fail_threshold=2,
    max_regenerations=3,   # 최대 3회 재시도
    disagreement_threshold=3
)

gate = EvaluationGateSOP(config=default_config)
```
