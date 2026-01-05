# FAQ 번역 에이전트 구현 가이드

이 문서는 AWS Bedrock 기반 다국어 FAQ 번역 워크플로우의 구현 가이드입니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처](#2-아키텍처)
3. [디렉토리 구조](#3-디렉토리-구조)
4. [핵심 개념](#4-핵심-개념)
5. [구현 단계](#5-구현-단계)
6. [데이터 모델](#6-데이터-모델)
7. [Skills 상세](#7-skills-상세)
8. [SOPs 상세](#8-sops-상세)
9. [Tools 상세](#9-tools-상세)
10. [워크플로우 상세](#10-워크플로우-상세)
11. [Best Practices](#11-best-practices)
12. [참고 자료](#12-참고-자료)
13. [용어집 및 스타일 가이드 관리](#13-용어집-및-스타일-가이드-관리)
14. [디버그 모드](#14-디버그-모드)
15. [프롬프트 캐싱](#15-프롬프트-캐싱-prompt-caching)

---

## 1. 프로젝트 개요

### 1.1 목표

- 45개 언어의 FAQ를 AWS Bedrock 기반으로 자동 번역
- 에이전트 기반 가드레일로 품질/리스크 관리
- 모든 서브 에이전트가 Pass일 때만 "번역 발행" 버튼 활성화

### 1.2 핵심 원칙

| 원칙 | 설명 |
|------|------|
| **보수적 품질 관리** | Fail/경계 점수는 자동 재생성 또는 PM 수동 검수로 루프백 |
| **지역별 리스크 반영** | 금칙어, 필수 면책, 금지 카테고리를 국가별로 관리 |
| **투명한 평가** | 모든 에이전트는 점수(0-5), 판정(Pass/Fail), 수정 제안을 구조화 |
| **추적 가능성** | 히스토리/대시보드를 통한 리스크 추세 관리 |

### 1.3 점수 체계

```
0-5 스케일 (낮은 정밀도가 더 일관적)

5점: 완벽
4점: 경미한 수정으로 자동 치유 가능 (Pass)
3점: 경계/인간 검수 필요 (Regenerate → HITL)
0-2점: Fail (즉시 차단)

자동 발행 요건: 모든 에이전트 점수 ≥ 4
```

---

## 2. 아키텍처

### 2.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRANSLATION PIPELINE                               │
└─────────────────────────────────────────────────────────────────────────────┘

     Step 1          Step 2          Step 3          Step 4          Step 5
    ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐
    │INPUT │───────▶│TRANS │───────▶│ BACK │───────▶│ EVAL │───────▶│ GATE │
    │      │        │ LATE │        │TRANS │        │(3개) │        │      │
    └──────┘        └──────┘        └──────┘        └──────┘        └──────┘
                       ▲                               │               │
                       │                               │               ▼
                       │                          ┌────┴────┐    ┌─────────┐
                       │                          │ 3 Agents│    │ DECIDE  │
                       │                          │ Parallel│    └────┬────┘
                       │                          └─────────┘         │
                       │                                              ▼
                       │         ┌────────────────────────────────────┴────────┐
                       │         │                    │                        │
                       │         ▼                    ▼                        ▼
                  ┌────┴───┐ ┌────────┐         ┌─────────┐              ┌─────────┐
                  │ RETRY  │ │  PASS  │         │ REVIEW  │              │  BLOCK  │
                  │(1 time)│ │Publish │         │PM Queue │              │ Reject  │
                  └────────┘ └────────┘         └─────────┘              └─────────┘
```

### 2.2 계층 구조

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ARCHITECTURE LAYERS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     3-TIER GUARDRAILS                               │  │
│   │   Input Guard → Runtime Guard → Output Guard (3 Evaluators)         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     STATE MACHINE                                   │  │
│   │   INIT → TRANSLATE → BACKTR → EVAL → DECIDE → [PASS/REGEN/HITL]    │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     MAKER-CHECKER LOOP                              │  │
│   │   Translator (Maker) ←→ Evaluators (Checker) - Max 1 iteration     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     SKILLS + SOPs + TOOLS                           │  │
│   │   Skills: 재사용 가능한 지식/프롬프트                                 │  │
│   │   SOPs: 의사결정 절차 (Python 코드)                                  │  │
│   │   Tools: Agent-as-Tool 래퍼                                         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 3개 평가 에이전트 (통합 구조)

기존 6개 에이전트를 3개로 통합하여 관리 효율성 향상:

| 에이전트 | 통합 영역 | 평가 내용 |
|----------|-----------|-----------|
| **ACCURACY** | 충실도 + 용어집 | 의미 보존, 역번역 검증, 용어 매핑, 포맷 무결성 |
| **COMPLIANCE** | 법률 + 안전 | 규제 준수, 금칙어, 면책문구, 콘텐츠 안전 |
| **QUALITY** | 문화 + A/B | 톤/격식, 문화 적합성, 후보 비교, 최종 선택 |

> **근거**: "To maintain effective control, consider limiting group chat orchestration to three or fewer agents." - [Microsoft Azure AI Agent Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

---

## 3. 디렉토리 구조

```
01_explainable_translate_agent/
├── IMPLEMENTATION_GUIDE.md          # 이 문서
├── config/
│   ├── languages.yaml               # 45개 언어 정의
│   ├── models.yaml                  # Bedrock 모델 ID
│   ├── thresholds.yaml              # 점수 임계값
│   └── risk_profiles/               # 국가별 리스크 프로파일
│       ├── US.yaml
│       ├── EU.yaml
│       ├── CN.yaml
│       └── ...
├── data/
│   ├── ko_faq.json                  # 한국어 원본 (기존)
│   ├── en-rUS_faq.json              # 미국 영어 (기존)
│   ├── en-rGB_faq.json              # 영국 영어 (기존)
│   └── glossaries/
│       └── abc_cloud/
│           ├── en-rUS.json
│           ├── ja.json
│           └── ...
├── skills/
│   ├── translator/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── style-guide.md
│   ├── accuracy-evaluator/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── scoring-examples.md
│   │       └── format-patterns.md
│   ├── compliance-evaluator/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── country-profiles.md
│   │       └── prohibited-terms.md
│   └── quality-evaluator/
│       ├── SKILL.md
│       └── references/
│           └── locale-guidelines.md
├── sops/
│   ├── __init__.py
│   ├── evaluation_gate.py           # Pass/Fail/Regenerate/Escalate 판정
│   ├── regeneration.py              # Maker-Checker 피드백 수집
│   ├── escalation.py                # PM 검수 라우팅
│   └── publishing.py                # 최종 발행 절차
├── src/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── translation_unit.py      # 번역 단위 스키마
│   │   ├── agent_result.py          # 에이전트 결과 스키마
│   │   └── workflow_state.py        # 상태 머신 정의
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── translator_tool.py
│   │   ├── backtranslator_tool.py
│   │   ├── accuracy_evaluator_tool.py
│   │   ├── compliance_evaluator_tool.py
│   │   └── quality_evaluator_tool.py
│   ├── prompts/
│   │   ├── template.py              # 프롬프트 템플릿 로더
│   │   ├── translator.md
│   │   ├── accuracy_evaluator.md
│   │   ├── compliance_evaluator.md
│   │   └── quality_evaluator.md
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── nodes.py                 # 워크플로우 노드
│   │   └── builder.py               # 그래프 빌더
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── input_guard.py           # 입력 검증
│   │   ├── runtime_guard.py         # 실행 모니터링
│   │   └── output_guard.py          # 출력 검증 (평가 에이전트)
│   └── utils/
│       ├── __init__.py
│       ├── bedrock_client.py        # Bedrock Converse API
│       ├── config_loader.py         # YAML 설정 로더
│       └── metrics.py               # 메트릭 수집
├── tests/
│   ├── test_sops.py
│   ├── test_evaluators.py
│   └── test_workflow.py
└── main.py                          # 엔트리포인트
```

---

## 4. 핵심 개념

### 4.1 Skill vs SOP vs Tool

| 개념 | 정의 | 특징 | 예시 |
|------|------|------|------|
| **Skill** | 재사용 가능한 지식/능력 패키지 | SKILL.md + references/ | `accuracy-evaluator` |
| **SOP** | 의사결정 절차 (Standard Operating Procedure) | Python 클래스, 테스트 가능 | `EvaluationGateSOP` |
| **Tool** | 실행 가능한 에이전트 래퍼 | Agent-as-Tool 패턴 | `accuracy_evaluator_tool` |

### 4.2 3-Tier Guardrails

```python
# Tier 1: INPUT GUARDS (사전 검증)
- 원문 언어 확인
- 길이 제한 검사
- PII 마스킹 확인
- 용어집/리스크 프로파일 로드

# Tier 2: RUNTIME GUARDS (실행 중 모니터링)
- 토큰 사용량 추적
- 타임아웃 관리
- 재시도 횟수 제한
- 모델 가용성 확인

# Tier 3: OUTPUT GUARDS (출력 검증)
- 3개 평가 에이전트 병렬 실행
- 점수 집계 및 판정
- 수정안 통합
```

### 4.3 State Machine

```python
class WorkflowState(Enum):
    INITIALIZED = auto()       # 초기화 완료
    TRANSLATING = auto()       # 번역 생성 중
    BACKTRANSLATING = auto()   # 역번역 중
    EVALUATING = auto()        # 3개 에이전트 평가 중
    DECIDING = auto()          # Release Guard 판정 중
    REGENERATING = auto()      # 재생성 중 (Maker-Checker Loop)
    PENDING_REVIEW = auto()    # PM 검수 대기
    APPROVED = auto()          # 승인 완료
    REJECTED = auto()          # 거부됨
    PUBLISHED = auto()         # 발행 완료
    FAILED = auto()            # 실패 (에러)
```

### 4.4 Maker-Checker Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MAKER-CHECKER LOOP                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐                      ┌─────────────┐                     │
│   │   MAKER     │                      │   CHECKER   │                     │
│   │ (Translator)│                      │(3 Evaluators)│                    │
│   └──────┬──────┘                      └──────┬──────┘                     │
│          │                                    │                             │
│          │  1. 번역 생성                       │                             │
│          ├────────────────────────────────────▶                             │
│          │                                    │                             │
│          │                     2. 평가 + 피드백│                             │
│          ◀────────────────────────────────────┤                             │
│          │                                    │                             │
│          │  3. 피드백 반영 재생성               │                             │
│          ├────────────────────────────────────▶                             │
│          │                                    │                             │
│          │                     4. 재평가       │                             │
│          ◀────────────────────────────────────┤                             │
│          │                                    │                             │
│          │         Loop until Pass or Max Attempts (1회)                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 구현 단계

### Phase 1: Foundation (기반)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 1.1 | 프로젝트 구조 생성 | 디렉토리, `__init__.py` | 없음 |
| 1.2 | 설정 파일 작성 | `config/*.yaml` | 없음 |
| 1.3 | 데이터 모델 정의 | `src/models/*.py` | 없음 |
| 1.4 | Bedrock 클라이언트 | `src/utils/bedrock_client.py` | 없음 |
| 1.5 | 프롬프트 템플릿 로더 | `src/prompts/template.py` | 없음 |

### Phase 2: Skills & Prompts (지식)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 2.1 | Translator Skill | `skills/translator/SKILL.md` | 없음 |
| 2.2 | Accuracy Evaluator Skill | `skills/accuracy-evaluator/` | 없음 |
| 2.3 | Compliance Evaluator Skill | `skills/compliance-evaluator/` | 없음 |
| 2.4 | Quality Evaluator Skill | `skills/quality-evaluator/` | 없음 |
| 2.5 | 프롬프트 파일 생성 | `src/prompts/*.md` | Skills |

### Phase 3: SOPs (의사결정)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 3.1 | Evaluation Gate SOP | `sops/evaluation_gate.py` | 데이터 모델 |
| 3.2 | Regeneration SOP | `sops/regeneration.py` | 데이터 모델 |
| 3.3 | Escalation SOP | `sops/escalation.py` | 데이터 모델 |
| 3.4 | Publishing SOP | `sops/publishing.py` | 데이터 모델 |
| 3.5 | SOP 단위 테스트 | `tests/test_sops.py` | SOPs |

### Phase 4: Tools (실행)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 4.1 | Translator Tool | `src/tools/translator_tool.py` | Skills, Bedrock |
| 4.2 | Backtranslator Tool | `src/tools/backtranslator_tool.py` | Skills, Bedrock |
| 4.3 | Accuracy Evaluator Tool | `src/tools/accuracy_evaluator_tool.py` | Skills, Bedrock |
| 4.4 | Compliance Evaluator Tool | `src/tools/compliance_evaluator_tool.py` | Skills, Bedrock |
| 4.5 | Quality Evaluator Tool | `src/tools/quality_evaluator_tool.py` | Skills, Bedrock |

### Phase 5: Guardrails (보호)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 5.1 | Input Guard | `src/guardrails/input_guard.py` | 데이터 모델 |
| 5.2 | Runtime Guard | `src/guardrails/runtime_guard.py` | 데이터 모델 |
| 5.3 | Output Guard | `src/guardrails/output_guard.py` | Tools |

### Phase 6: Orchestration (조율)

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 6.1 | 워크플로우 노드 | `src/graph/nodes.py` | Tools, SOPs |
| 6.2 | 그래프 빌더 | `src/graph/builder.py` | 노드 |
| 6.3 | HITL 통합 | PM 검수 폴링 | 그래프 |
| 6.4 | 메인 엔트리포인트 | `main.py` | 모든 컴포넌트 |

### Phase 7: Testing & Integration

| 순서 | 작업 | 산출물 | 의존성 |
|------|------|--------|--------|
| 7.1 | 단위 테스트 | `tests/test_*.py` | 각 컴포넌트 |
| 7.2 | 통합 테스트 | E2E 테스트 | 전체 시스템 |
| 7.3 | 배치 처리 | 45개 언어 처리 | 통합 테스트 |

---

## 6. 데이터 모델

### 6.1 TranslationUnit (입력)

```python
# src/models/translation_unit.py

from pydantic import BaseModel
from typing import Optional, Dict, List

class TranslationUnit(BaseModel):
    """번역 단위 - 단일 FAQ 항목"""

    # 필수 필드
    key: str                          # FAQ 키 (예: IDS_FAQ_SC_ABOUT)
    source_text: str                  # 원문 (한국어)
    source_lang: str                  # 원본 언어 (ko)
    target_lang: str                  # 대상 언어 (en-rUS)

    # 컨텍스트
    glossary: Dict[str, str] = {}     # 용어집 매핑
    risk_profile: str = "DEFAULT"     # 국가별 리스크 프로파일
    style_guide: Dict[str, str] = {}  # 톤/격식 가이드

    # 메타데이터
    faq_version: str = "v1.0"
    glossary_version: str = "v1.0"
    product: str = "abc_cloud"
```

### 6.2 AgentResult (평가 결과)

```python
# src/models/agent_result.py

from pydantic import BaseModel
from typing import List, Dict, Literal, Optional

class Correction(BaseModel):
    """수정 제안"""
    original: str
    suggested: str
    reason: str

class AgentResult(BaseModel):
    """평가 에이전트 결과"""

    # 에이전트 식별
    agent_name: str                   # accuracy, compliance, quality

    # Chain-of-Thought (평가 과정)
    reasoning_chain: List[str]        # Step별 분석 결과

    # 최종 판정
    score: int                        # 0-5
    verdict: Literal["pass", "fail", "review"]

    # 상세 정보
    issues: List[str] = []            # 발견된 문제점
    corrections: List[Correction] = [] # 수정 제안

    # 메타데이터
    token_usage: Dict[str, int] = {}  # 토큰 사용량
    latency_ms: int = 0               # 응답 시간
```

### 6.3 GateDecision (게이트 판정)

```python
# src/models/gate_decision.py

from pydantic import BaseModel
from typing import List, Dict, Optional
from enum import Enum

class Verdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    REGENERATE = "regenerate"
    ESCALATE = "escalate"

class GateDecision(BaseModel):
    """평가 게이트 판정 결과"""

    # 최종 판정
    verdict: Verdict
    can_publish: bool

    # 점수 정보
    scores: Dict[str, int]            # 에이전트별 점수
    min_score: int
    avg_score: float

    # Chain-of-Thought
    reasoning_chains: Dict[str, List[str]]

    # 상세 정보
    blocker_agent: Optional[str] = None
    review_agents: List[str] = []
    corrections: List[dict] = []
    message: str = ""

    # 메트릭
    agent_agreement_score: float = 1.0  # 에이전트 간 일치도
    total_latency_ms: int = 0
```

### 6.4 TranslationRecord (전체 기록)

```python
# src/models/translation_record.py

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TranslationRecord(BaseModel):
    """번역 전체 기록 (저장용)"""

    # 식별자
    id: str                           # UUID
    unit: TranslationUnit

    # 번역 데이터
    candidates: List[str]             # 1-2개 번역 후보
    selected_candidate: int           # 선택된 후보 인덱스
    backtranslation: str
    final_translation: str

    # 평가 결과
    agent_results: List[AgentResult]
    gate_decision: GateDecision

    # 워크플로우 정보
    attempt_count: int                # 시도 횟수
    workflow_state: str               # 최종 상태

    # PM 검수 (해당 시)
    pm_review: Optional[dict] = None

    # 타임스탬프
    created_at: datetime
    published_at: Optional[datetime] = None
```

---

## 7. Skills 상세

### 7.1 Skill 구조

```
skill-name/
├── SKILL.md              # 메인 지침 (필수)
└── references/           # 참조 문서 (선택)
    ├── examples.md       # Few-shot 예시
    └── guidelines.md     # 상세 가이드라인
```

### 7.2 Accuracy Evaluator Skill

```markdown
# skills/accuracy-evaluator/SKILL.md

---
name: accuracy-evaluator
description: 번역의 정확성을 평가하는 Skill. 의미 충실도(역번역 활용)와
             용어집/포맷 무결성을 통합 평가합니다.
---

# 정확성 평가 Skill

## Role
<role>
당신은 번역 정확성 평가 전문가입니다. 두 가지 관점에서 평가합니다:
1. **의미 충실도**: 원문의 의미가 정확히 전달되었는가?
2. **용어/포맷 무결성**: 용어집과 포맷이 올바르게 적용되었는가?
</role>

## Behavior
<behavior>
<chain_of_thought>
최종 점수를 부여하기 전에 반드시 평가 과정을 단계별로 설명하세요.
이는 점수의 일관성과 투명성을 높입니다.
</chain_of_thought>

<investigate_before_answering>
역번역을 반드시 원문과 비교하여 의미 손실/추가를 확인하세요.
추측하지 말고 실제 비교 결과에 기반하여 판단하세요.
</investigate_before_answering>
</behavior>

## 평가 절차
<instructions>
**Step 1: 의미 분석**
- 원문과 번역문의 핵심 의미 비교
- 역번역과 원문의 일치도 분석
- 의미 손실/추가/왜곡 감지

**Step 2: 용어 검증**
- 용어집 매핑 확인
- 브랜드명/제품명 정확성
- 플레이스홀더 보존 확인

**Step 3: 포맷 검증**
- HTML 태그 무결성 (<a>, </a>)
- 숫자/날짜/단위 보존
- 링크 구조 확인

**Step 4: 최종 판정**
- 종합 점수 부여 (0-5)
- 문제점 및 수정안 제시
</instructions>

## 점수 기준
<scoring>
- **5점**: 의미/용어/포맷 완벽
  - 역번역이 원문과 의미적으로 동일
  - 모든 용어집 항목 정확히 적용
  - 포맷 요소 100% 보존

- **4점**: 경미한 수정 필요 (Pass)
  - 뉘앙스/어순에 미세한 차이
  - 용어 1건 미적용 또는 대체 표현 사용
  - 포맷 완전

- **3점**: 검수 필요 (PM 에스컬레이션)
  - 핵심 의미 일부 누락 또는 추가
  - 용어 다수 미적용
  - 플레이스홀더 1건 누락

- **2점**: 수정 필수
  - 의미 왜곡 존재
  - 브랜드명 오기
  - 포맷 손상

- **1점**: 심각한 오류
  - 완전한 오역
  - 법적 명칭 오류

- **0점**: 사용 불가
  - 원문과 무관한 내용
  - 모든 포맷 손실
</scoring>

## Few-shot 예시
<examples>
예시는 `references/scoring-examples.md` 파일을 참조하세요.
</examples>

## 출력 형식
<output_format>
반드시 아래 형식을 따르세요:

**평가 과정:**
[Step 1-4의 분석 내용]

**최종 결과:**
```json
{
  "reasoning_chain": [
    "Step 1: [의미 분석 요약]",
    "Step 2: [용어 검증 요약]",
    "Step 3: [포맷 검증 요약]"
  ],
  "score": 4,
  "verdict": "pass",
  "issues": ["발견된 문제점"],
  "corrections": [
    {
      "original": "현재 문장",
      "suggested": "수정 제안",
      "reason": "수정 이유"
    }
  ]
}
```
</output_format>

## 주의사항
<constraints>
- 스타일/톤의 차이는 이 평가에서 고려하지 않음 (Quality Skill 담당)
- 법률/규제 준수 여부는 이 평가에서 고려하지 않음 (Compliance Skill 담당)
- 오직 **정확성**에만 집중
</constraints>
```

### 7.3 Few-shot 예시 파일

```markdown
# skills/accuracy-evaluator/references/scoring-examples.md

# 점수별 평가 예시

## 5점 예시 (완벽)

<example score="5">
**원문**: ABC 클라우드는 사용자의 ABC 계정과 연동된 정보를 동기화합니다.
**번역**: ABC Cloud syncs information linked to your ABC account.
**역번역**: ABC 클라우드는 ABC 계정에 연결된 정보를 동기화합니다.

**평가 과정**:
- Step 1: 원문과 역번역의 핵심 의미 완전 일치
- Step 2: "ABC 클라우드" → "ABC Cloud" 용어집 정확 적용
- Step 3: 특수 포맷 없음, 해당 없음

**판정**: 의미, 용어, 포맷 모두 완벽. 5점.
</example>

## 4점 예시 (경미한 수정)

<example score="4">
**원문**: 데이터를 백업하고 복원할 수 있습니다.
**번역**: You can backup and restore your data.
**역번역**: 데이터를 백업하고 복원할 수 있습니다.

**평가 과정**:
- Step 1: 의미 완전 일치
- Step 2: "backup" → 용어집에서 "back up" (두 단어)로 권장
- Step 3: 포맷 완전

**판정**: 경미한 용어 차이. 수정 후 사용 가능. 4점.

**수정 제안**:
- original: "backup"
- suggested: "back up"
- reason: 용어집 표준 용어
</example>

## 3점 예시 (검수 필요)

<example score="3">
**원문**: 24시간 내에 반드시 설치하세요.
**번역**: You must install within 24 hours guaranteed.
**역번역**: 24시간 내에 반드시 설치하세요, 보장됨.

**평가 과정**:
- Step 1: "guaranteed" 추가됨 (원문에 없는 표현)
- Step 2: 용어 적용 해당 없음
- Step 3: 포맷 완전

**판정**: 의미 추가 발생. PM 검수 필요. 3점.
</example>

## 1점 예시 (심각한 오류)

<example score="1">
**원문**: 데이터 삭제 후 복구할 수 없습니다.
**번역**: You can recover your data after deletion.
**역번역**: 삭제 후 데이터를 복구할 수 있습니다.

**평가 과정**:
- Step 1: 의미 완전 반대! "복구 불가" → "복구 가능"으로 오역
- Step 2: 해당 없음
- Step 3: 해당 없음

**판정**: 심각한 오역. 사용자 오해 유발 가능. 1점.
</example>
```

---

## 8. SOPs 상세

### 8.1 Evaluation Gate SOP

```python
# sops/evaluation_gate.py

"""
평가 게이트 SOP

목적: 3개 평가 에이전트의 결과를 기반으로 번역의 최종 판정을 결정

비즈니스 규칙:
- 모든 에이전트 점수 ≥ 4: Auto-Pass (발행 가능)
- 하나라도 점수 ≤ 2: Block (즉시 차단)
- 하나라도 점수 = 3:
  - 첫 번째 시도: Regenerate (재생성)
  - 두 번째 시도 이후: Escalate (PM 검수)
- 에이전트 간 점수 차이 ≥ 2: 불일치로 간주 → Escalate
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum

from src.models.agent_result import AgentResult
from src.models.gate_decision import GateDecision, Verdict


class EvaluationGateSOP:
    """평가 게이트 SOP"""

    # 비즈니스 규칙 (설정 가능)
    PASS_THRESHOLD = 4
    FAIL_THRESHOLD = 2
    MAX_REGENERATIONS = 1
    DISAGREEMENT_THRESHOLD = 2  # 에이전트 간 불일치 임계값

    def decide(
        self,
        agent_results: List[AgentResult],
        attempt_count: int,
        start_time: Optional[datetime] = None
    ) -> GateDecision:
        """
        평가 결과를 기반으로 최종 판정

        Args:
            agent_results: 3개 에이전트의 평가 결과
            attempt_count: 현재 시도 횟수 (1부터 시작)
            start_time: 평가 시작 시간 (메트릭용)

        Returns:
            GateDecision: 최종 판정 결과
        """
        scores = {r.agent_name: r.score for r in agent_results}
        min_score = min(scores.values())
        max_score = max(scores.values())
        avg_score = sum(scores.values()) / len(scores)

        # 에이전트 간 일치도
        disagreement = max_score - min_score
        agreement_score = 1.0 - (disagreement / 5.0)

        # CoT 통합
        reasoning_chains = {
            r.agent_name: r.reasoning_chain
            for r in agent_results
        }

        # 수정안 통합
        all_corrections = []
        for r in agent_results:
            all_corrections.extend([c.dict() for c in r.corrections])

        # 레이턴시 계산
        total_latency = sum(r.latency_ms for r in agent_results)

        # Case 1: 모든 에이전트 통과
        if all(s >= self.PASS_THRESHOLD for s in scores.values()):
            return GateDecision(
                verdict=Verdict.PASS,
                can_publish=True,
                scores=scores,
                min_score=min_score,
                avg_score=avg_score,
                reasoning_chains=reasoning_chains,
                corrections=all_corrections,
                message="모든 에이전트 통과. 발행 가능.",
                agent_agreement_score=agreement_score,
                total_latency_ms=total_latency
            )

        # Case 2: 치명적 실패
        if any(s <= self.FAIL_THRESHOLD for s in scores.values()):
            blocker = next(
                r for r in agent_results
                if r.score <= self.FAIL_THRESHOLD
            )
            return GateDecision(
                verdict=Verdict.BLOCK,
                can_publish=False,
                scores=scores,
                min_score=min_score,
                avg_score=avg_score,
                reasoning_chains=reasoning_chains,
                blocker_agent=blocker.agent_name,
                corrections=all_corrections,
                message=f"차단: {blocker.agent_name}",
                agent_agreement_score=agreement_score,
                total_latency_ms=total_latency
            )

        # Case 3: 에이전트 간 심각한 불일치
        if disagreement >= self.DISAGREEMENT_THRESHOLD:
            return GateDecision(
                verdict=Verdict.ESCALATE,
                can_publish=False,
                scores=scores,
                min_score=min_score,
                avg_score=avg_score,
                reasoning_chains=reasoning_chains,
                review_agents=list(scores.keys()),
                corrections=all_corrections,
                message=f"에이전트 불일치 ({disagreement}점 차이). PM 검수 필요.",
                agent_agreement_score=agreement_score,
                total_latency_ms=total_latency
            )

        # Case 4: 경계 점수 - Maker-Checker Loop
        borderline_agents = [
            name for name, score in scores.items()
            if score == 3
        ]

        if attempt_count <= self.MAX_REGENERATIONS:
            return GateDecision(
                verdict=Verdict.REGENERATE,
                can_publish=False,
                scores=scores,
                min_score=min_score,
                avg_score=avg_score,
                reasoning_chains=reasoning_chains,
                review_agents=borderline_agents,
                corrections=all_corrections,
                message=f"재생성 시도 ({attempt_count}/{self.MAX_REGENERATIONS})",
                agent_agreement_score=agreement_score,
                total_latency_ms=total_latency
            )

        # Case 5: 재생성 후에도 경계 → PM 에스컬레이션
        return GateDecision(
            verdict=Verdict.ESCALATE,
            can_publish=False,
            scores=scores,
            min_score=min_score,
            avg_score=avg_score,
            reasoning_chains=reasoning_chains,
            review_agents=borderline_agents,
            corrections=all_corrections,
            message=f"PM 검수 필요: {', '.join(borderline_agents)}",
            agent_agreement_score=agreement_score,
            total_latency_ms=total_latency
        )
```

### 8.2 Regeneration SOP

```python
# sops/regeneration.py

"""
재생성 SOP

목적: 경계 점수 발생 시 이전 문제점을 피드백으로 제공하여 번역 재생성

Maker-Checker 패턴:
- Checker (평가 에이전트)가 제공한 피드백을 수집
- Maker (번역 에이전트)에게 피드백 전달
- 피드백 반영하여 새로운 번역 생성
"""

from dataclasses import dataclass
from typing import List, Dict

from src.models.agent_result import AgentResult, Correction


@dataclass
class RegenerationFeedback:
    """재생성을 위한 피드백 구조"""
    previous_issues: List[str]
    corrections: List[Correction]
    agent_feedbacks: Dict[str, List[str]]  # agent_name -> reasoning_chain


class RegenerationSOP:
    """재생성 절차를 관리하는 SOP"""

    def collect_feedback(
        self,
        agent_results: List[AgentResult]
    ) -> RegenerationFeedback:
        """
        평가 결과에서 재생성을 위한 피드백 수집

        통과하지 못한 에이전트 (score < 4)의 피드백만 수집
        """
        issues = []
        corrections = []
        agent_feedbacks = {}

        for result in agent_results:
            if result.score < 4:
                issues.extend(result.issues)
                corrections.extend(result.corrections)
                agent_feedbacks[result.agent_name] = result.reasoning_chain

        return RegenerationFeedback(
            previous_issues=issues,
            corrections=corrections,
            agent_feedbacks=agent_feedbacks
        )

    def format_feedback_for_prompt(
        self,
        feedback: RegenerationFeedback
    ) -> str:
        """
        피드백을 번역 프롬프트에 주입할 형태로 포맷
        """
        lines = [
            "<previous_feedback>",
            "이전 번역에서 다음 문제가 발견되었습니다:",
            ""
        ]

        # 문제점 나열
        for i, issue in enumerate(feedback.previous_issues, 1):
            lines.append(f"{i}. {issue}")

        # 수정 제안
        if feedback.corrections:
            lines.append("")
            lines.append("수정 제안:")
            for correction in feedback.corrections:
                lines.append(f"- '{correction.original}' → '{correction.suggested}'")
                lines.append(f"  이유: {correction.reason}")

        lines.append("")
        lines.append("위 문제점을 피하여 다시 번역하세요.")
        lines.append("</previous_feedback>")

        return "\n".join(lines)
```

---

## 9. Tools 상세

### 9.1 Tool 구현 패턴

```python
# src/tools/accuracy_evaluator_tool.py

"""
정확성 평가 Tool

Skill: accuracy-evaluator
SOP: evaluation_gate (점수 판정에 사용)
"""

import asyncio
import json
import logging
from typing import Any, Annotated

from src.utils.bedrock_client import BedrockClient
from src.prompts.template import apply_prompt_template
from src.models.agent_result import AgentResult, Correction

logger = logging.getLogger(__name__)


TOOL_SPEC = {
    "name": "accuracy_evaluator_tool",
    "description": "번역의 정확성을 평가합니다. 의미 충실도와 용어/포맷 무결성을 검증합니다.",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "source_text": {
                    "type": "string",
                    "description": "원문 (한국어)"
                },
                "translation": {
                    "type": "string",
                    "description": "번역문"
                },
                "backtranslation": {
                    "type": "string",
                    "description": "역번역문"
                },
                "glossary": {
                    "type": "object",
                    "description": "용어집 매핑"
                }
            },
            "required": ["source_text", "translation", "backtranslation"]
        }
    }
}


async def evaluate_accuracy(
    source_text: str,
    translation: str,
    backtranslation: str,
    glossary: dict = None,
    bedrock_client: BedrockClient = None
) -> AgentResult:
    """
    정확성 평가 실행

    Returns:
        AgentResult: 평가 결과
    """
    import time
    start_time = time.time()

    # 프롬프트 구성
    system_prompt = apply_prompt_template(
        prompt_name="accuracy_evaluator",
        prompt_context={}
    )

    user_message = f"""
다음 번역을 평가해주세요.

<source_text>
{source_text}
</source_text>

<translation>
{translation}
</translation>

<backtranslation>
{backtranslation}
</backtranslation>

<glossary>
{json.dumps(glossary or {}, ensure_ascii=False)}
</glossary>

위 내용을 바탕으로 정확성을 평가하고 결과를 JSON 형식으로 반환하세요.
"""

    # Bedrock 호출
    response = await bedrock_client.converse_async(
        system_prompt=system_prompt,
        user_message=user_message,
        model_id="anthropic.claude-sonnet-4-5-20250929-v1:0"
    )

    # 응답 파싱
    result = _parse_evaluation_response(response.text)

    # 메타데이터 추가
    result.agent_name = "accuracy"
    result.latency_ms = int((time.time() - start_time) * 1000)
    result.token_usage = {
        "input": response.input_tokens,
        "output": response.output_tokens
    }

    return result


def _parse_evaluation_response(response_text: str) -> AgentResult:
    """응답 파싱"""
    import re

    # JSON 블록 추출
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        json_str = json_match.group() if json_match else "{}"

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        data = {
            "score": 0,
            "verdict": "fail",
            "issues": ["평가 결과 파싱 실패"],
            "reasoning_chain": [response_text]
        }

    # Correction 객체 변환
    corrections = [
        Correction(**c) for c in data.get("corrections", [])
    ]

    return AgentResult(
        agent_name="",  # 호출자가 설정
        reasoning_chain=data.get("reasoning_chain", []),
        score=data.get("score", 0),
        verdict=data.get("verdict", "fail"),
        issues=data.get("issues", []),
        corrections=corrections
    )
```

---

## 10. 워크플로우 상세

### 10.1 워크플로우 노드

```python
# src/graph/nodes.py

"""
워크플로우 노드 정의

각 노드는 하나의 단계를 담당:
- translate_node: 번역 생성
- backtranslate_node: 역번역
- evaluate_node: 3개 에이전트 병렬 평가
- decide_node: Release Guard 판정
- regenerate_node: 재생성 (피드백 반영)
"""

import asyncio
from typing import Dict, Any
from datetime import datetime

from src.models.translation_unit import TranslationUnit
from src.models.agent_result import AgentResult
from src.models.gate_decision import GateDecision, Verdict
from src.tools.translator_tool import translate
from src.tools.backtranslator_tool import backtranslate
from src.tools.accuracy_evaluator_tool import evaluate_accuracy
from src.tools.compliance_evaluator_tool import evaluate_compliance
from src.tools.quality_evaluator_tool import evaluate_quality
from sops.evaluation_gate import EvaluationGateSOP
from sops.regeneration import RegenerationSOP


# 글로벌 상태 (managed-agentcore 패턴)
_global_node_states: Dict[str, Any] = {}


async def translate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """번역 생성 노드"""
    unit: TranslationUnit = state["unit"]
    feedback = state.get("feedback")  # 재생성 시 피드백

    # 번역 생성 (2개 후보)
    candidates = await translate(
        source_text=unit.source_text,
        source_lang=unit.source_lang,
        target_lang=unit.target_lang,
        glossary=unit.glossary,
        style_guide=unit.style_guide,
        feedback=feedback,
        num_candidates=2
    )

    state["candidates"] = candidates
    state["workflow_state"] = "TRANSLATING"
    return state


async def backtranslate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """역번역 노드"""
    candidates = state["candidates"]
    unit: TranslationUnit = state["unit"]

    # 첫 번째 후보 역번역
    backtranslation = await backtranslate(
        text=candidates[0],
        source_lang=unit.target_lang,
        target_lang=unit.source_lang
    )

    state["backtranslation"] = backtranslation
    state["workflow_state"] = "BACKTRANSLATING"
    return state


async def evaluate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """평가 노드 (3개 에이전트 병렬)"""
    unit: TranslationUnit = state["unit"]
    translation = state["candidates"][0]
    backtranslation = state["backtranslation"]

    start_time = datetime.now()

    # 3개 에이전트 병렬 실행
    results = await asyncio.gather(
        evaluate_accuracy(
            source_text=unit.source_text,
            translation=translation,
            backtranslation=backtranslation,
            glossary=unit.glossary
        ),
        evaluate_compliance(
            source_text=unit.source_text,
            translation=translation,
            risk_profile=unit.risk_profile
        ),
        evaluate_quality(
            source_text=unit.source_text,
            translation=translation,
            candidates=state["candidates"],
            target_lang=unit.target_lang
        )
    )

    state["agent_results"] = results
    state["eval_start_time"] = start_time
    state["workflow_state"] = "EVALUATING"
    return state


async def decide_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """판정 노드 (Release Guard)"""
    agent_results = state["agent_results"]
    attempt_count = state.get("attempt_count", 1)
    eval_start_time = state.get("eval_start_time")

    # SOP 실행
    gate_sop = EvaluationGateSOP()
    decision = gate_sop.decide(
        agent_results=agent_results,
        attempt_count=attempt_count,
        start_time=eval_start_time
    )

    state["gate_decision"] = decision
    state["workflow_state"] = "DECIDING"
    return state


async def regenerate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """재생성 준비 노드"""
    agent_results = state["agent_results"]

    # 피드백 수집
    regen_sop = RegenerationSOP()
    feedback = regen_sop.collect_feedback(agent_results)
    feedback_text = regen_sop.format_feedback_for_prompt(feedback)

    state["feedback"] = feedback_text
    state["attempt_count"] = state.get("attempt_count", 1) + 1
    state["workflow_state"] = "REGENERATING"
    return state
```

### 10.2 그래프 빌더

```python
# src/graph/builder.py

"""
워크플로우 그래프 빌더

State Machine 기반으로 조건부 라우팅 구현
"""

from typing import Dict, Any

from src.graph.nodes import (
    translate_node,
    backtranslate_node,
    evaluate_node,
    decide_node,
    regenerate_node
)
from src.models.gate_decision import Verdict


def should_regenerate(state: Dict[str, Any]) -> bool:
    """재생성 조건"""
    decision = state.get("gate_decision")
    return decision and decision.verdict == Verdict.REGENERATE


def should_escalate(state: Dict[str, Any]) -> bool:
    """PM 에스컬레이션 조건"""
    decision = state.get("gate_decision")
    return decision and decision.verdict == Verdict.ESCALATE


def should_pass(state: Dict[str, Any]) -> bool:
    """통과 조건"""
    decision = state.get("gate_decision")
    return decision and decision.verdict == Verdict.PASS


def should_block(state: Dict[str, Any]) -> bool:
    """차단 조건"""
    decision = state.get("gate_decision")
    return decision and decision.verdict == Verdict.BLOCK


class TranslationWorkflowGraph:
    """번역 워크플로우 그래프"""

    async def run(self, unit: 'TranslationUnit') -> Dict[str, Any]:
        """워크플로우 실행"""
        state = {
            "unit": unit,
            "attempt_count": 1,
            "workflow_state": "INITIALIZED"
        }

        while True:
            # Step 1: 번역
            state = await translate_node(state)

            # Step 2: 역번역
            state = await backtranslate_node(state)

            # Step 3: 평가
            state = await evaluate_node(state)

            # Step 4: 판정
            state = await decide_node(state)

            # Step 5: 라우팅
            if should_pass(state):
                state["workflow_state"] = "APPROVED"
                break

            if should_block(state):
                state["workflow_state"] = "REJECTED"
                break

            if should_escalate(state):
                state["workflow_state"] = "PENDING_REVIEW"
                # TODO: PM 검수 폴링
                break

            if should_regenerate(state):
                state = await regenerate_node(state)
                # Loop back to translate
                continue

            # 예상치 못한 상태
            state["workflow_state"] = "FAILED"
            break

        return state
```

---

## 11. Best Practices

### 11.1 LLM-as-Judge

| Practice | 설명 | 근거 |
|----------|------|------|
| **Chain-of-Thought** | 점수 전에 평가 과정 설명 | 80%+ 인간 일치율 |
| **Few-shot 예시** | 2-3개 다양한 예시 제공 | 12.6% 정확도 향상 |
| **낮은 정밀도 스케일** | 0-5 스케일 사용 | 일관성 향상 |
| **Pairwise + Pointwise** | A/B 비교 + 상세 점수 | 안정성 + 상세 피드백 |

### 11.2 Multi-Agent Orchestration

| Practice | 설명 | 근거 |
|----------|------|------|
| **3개 이하 에이전트** | 그룹 토론 시 제한 | 제어 효과성 |
| **State Machine** | 명시적 상태/전이 | 신뢰성 향상 |
| **Maker-Checker Loop** | 반복적 개선 | 품질 향상 |
| **Parallel Execution** | 독립 작업 동시 실행 | 시간 단축 |

### 11.3 Guardrails

| Practice | 설명 | 근거 |
|----------|------|------|
| **3-Tier 구조** | Input/Runtime/Output | 다층 방어 |
| **자동 재시도** | 피드백 반영 재생성 | 품질 개선 |
| **HITL 에스컬레이션** | 경계 케이스 인간 검수 | 리스크 관리 |
| **메트릭 추적** | 지연시간, 토큰, 일치도 | 모니터링 |

---

## 12. 참고 자료

### 12.1 외부 문서

- [LLM-as-a-Judge Complete Guide - Evidently AI](https://www.evidentlyai.com/llm-guide/llm-as-a-judge)
- [Using LLMs for Evaluation - Cameron Wolfe](https://cameronrwolfe.substack.com/p/llm-as-a-judge)
- [LLM Evaluation Best Practices - Databricks](https://www.databricks.com/blog/LLM-auto-eval-best-practices-RAG)
- [AI Agent Orchestration Patterns - Microsoft Azure](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- [LLM Orchestration Best Practices 2025 - orq.ai](https://orq.ai/blog/llm-orchestration)
- [Multi-Agent Orchestration on AWS](https://aws.amazon.com/solutions/guidance/multi-agent-orchestration-on-aws/)
- [Guardrails in GenAI - Medium](https://medium.com/@ajayverma23/the-ultimate-guide-to-guardrails-in-genai)

### 12.2 내부 참조

- `/home/ubuntu/sample-deep-insight/managed-agentcore` - 에이전트 코어 참조 구현
- `/home/ubuntu/sample-deep-insight/self-hosted/skills` - Skill 작성 가이드
- `/home/ubuntu/explainable-translate-agent/01_compare_model` - 번역 품질 평가 참조

### 12.3 AWS Bedrock 모델 ID

```yaml
# config/models.yaml
models:
  translator:
    model_id: "anthropic.claude-sonnet-4-5-20250929-v1:0"
    region: "us-west-2"

  evaluator:
    model_id: "anthropic.claude-sonnet-4-5-20250929-v1:0"
    region: "us-west-2"

  backtranslator:
    model_id: "anthropic.claude-haiku-4-5-20251001-v1:0"  # 빠른 모델
    region: "us-west-2"
```

---

## 13. 용어집 및 스타일 가이드 관리

### 13.1 개요

번역 일관성을 위해 용어집(Glossary)과 스타일 가이드(Style Guide)를 외부 파일로 관리합니다.
`product`와 `target_lang`을 기반으로 자동 로드됩니다.

### 13.2 디렉토리 구조

```
data/
├── glossaries/
│   └── abc_cloud/
│       ├── en.yaml          # 영어 용어집
│       ├── ja.yaml          # 일본어 용어집
│       └── ...
└── style_guides/
    └── abc_cloud/
        ├── en.yaml          # 영어 스타일 가이드
        ├── ja.yaml          # 일본어 스타일 가이드
        └── ...
```

### 13.3 용어집 형식

```yaml
# data/glossaries/abc_cloud/en.yaml

# ABC Cloud 용어집 (Korean → English)
# 번역 시 일관성을 위한 필수 용어 매핑

# 제품명
ABC 클라우드: ABC Cloud
ABC 계정: ABC account

# 핵심 기능
동기화: sync
백업: backup
복원: restore

# UI 요소
설정: Settings
앱: app
```

### 13.4 스타일 가이드 형식

```yaml
# data/style_guides/abc_cloud/en.yaml

# ABC Cloud 스타일 가이드 (English)
tone: formal
voice: active
formality: professional
sentence_style: concise
```

### 13.5 자동 로드 로직

`translate_node`에서 `product`와 `target_lang`을 기반으로 자동 로드:

```python
# src/graph/nodes.py

from src.utils.config import get_glossary, get_style_guide

async def translate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    unit: TranslationUnit = state["unit"]

    # 용어집/스타일 가이드 자동 로드
    glossary = get_glossary(unit.product, unit.target_lang)
    style_guide = get_style_guide(unit.product, unit.target_lang)

    result = await translate(
        source_text=unit.source_text,
        glossary=glossary,
        style_guide=style_guide,
        ...
    )
```

### 13.6 프롬프트 주입

`translator_tool.py`에서 용어집과 스타일 가이드를 시스템 프롬프트에 주입:

```python
def _build_system_prompt(...):
    # 용어집 포맷
    if glossary:
        glossary_lines = [f"- {src} → {tgt}" for src, tgt in glossary.items()]
        glossary_text = "\n".join(glossary_lines)
    else:
        glossary_text = "(용어집 없음)"

    # 스타일 가이드 포맷
    if style_guide:
        style_lines = [f"- {k}: {v}" for k, v in style_guide.items()]
        style_text = "\n".join(style_lines)
    else:
        style_text = "(기본 스타일)"

    # 프롬프트 템플릿에 주입
    return load_prompt(
        "translator",
        glossary=glossary_text,
        style_guide=style_text,
        ...
    )
```

### 13.7 언어 코드 정규화

`en-rUS` → `en`으로 정규화하여 파일 검색:

```python
# src/utils/config.py

def load_glossary(self, product: str, target_lang: str):
    base_lang = target_lang.split("-")[0]  # "en-rUS" → "en"

    candidates = [
        f"{target_lang}.yaml",  # 정확히 일치 (en-rUS.yaml)
        f"{base_lang}.yaml",    # 기본 언어 (en.yaml)
    ]
```

---

## 14. 디버그 모드

### 14.1 --debug 옵션

프롬프트 내용을 확인하려면 `--debug` 플래그 사용:

```bash
uv run --no-sync python test_workflow.py --input examples/single/faq.json --debug
```

### 14.2 출력 예시

```
============================================================
[Translator] (IDS_FAQ_SYNC_001) SYSTEM PROMPT
============================================================
## Role
<role>
You are a professional translator specializing in ABC Cloud product documentation.
Translate the source text from ko to en-rUS.
</role>

## Glossary
<glossary>
Apply these term mappings exactly:

- ABC 클라우드 → ABC Cloud
- 동기화 → sync
- 네트워크 → network
- 앱 → app
</glossary>

## Style Guide
<style_guide>
- tone: formal
- voice: active
- formality: professional
- sentence_style: concise
</style_guide>
...
============================================================

============================================================
[Translator] (IDS_FAQ_SYNC_001) USER PROMPT
============================================================
<source_text>
ABC 클라우드에서 동기화가 되지 않을 경우, 네트워크 연결 상태를 확인하고 앱을 재시작해 주세요.
</source_text>
============================================================
```

### 14.3 배치 실행 시 key 구분

배치 실행 시 각 항목의 key가 로그에 포함되어 구분 가능:

```
[Translator] (IDS_UI_BACKUP_BTN) SYSTEM PROMPT
[Translator] (IDS_UI_BACKUP_BTN) USER PROMPT
[Translator] (IDS_FAQ_RESTORE_001) SYSTEM PROMPT
[Translator] (IDS_FAQ_RESTORE_001) USER PROMPT
```

### 14.4 구현 위치

- `test_workflow.py`: `--debug` 인자 파싱 및 로그 레벨 설정
- `src/tools/translator_tool.py`: 시스템/유저 프롬프트 DEBUG 로깅

---

## 15. 프롬프트 캐싱 (Prompt Caching)

### 15.1 개요

AWS Bedrock의 프롬프트 캐싱을 사용하여 동일한 시스템 프롬프트 재사용 시 **비용 90% 절감**.

### 15.2 모델별 최소 토큰 요구사항

| 모델 | 최소 토큰 | 최대 체크포인트 | 캐싱 지원 |
|------|----------|----------------|----------|
| **Claude Opus 4.5** | 4,096 | 4 | ✅ |
| **Claude Sonnet 4.5** | 1,024 | 4 | ✅ |
| Claude 3.5 Haiku | 2,048 | 4 | ✅ |
| Amazon Nova | 1,024 | 4 | ✅ |

### 15.3 비용 구조

| 유형 | 비용 | 설명 |
|------|------|------|
| `cache_write` | +25% | 캐시 생성 시 (첫 요청) |
| `cache_read` | -90% | 캐시 히트 시 (후속 요청) |

### 15.4 현재 설정

시스템 프롬프트 크기와 모델별 캐싱 적용 여부:

| 에이전트 | 프롬프트 크기 | 현재 모델 | 캐싱 |
|----------|-------------|----------|------|
| Translator | ~2,000 tokens | Opus 4.5 | ❌ (4,096 필요) |
| Compliance | ~1,800 tokens | Opus 4.5 | ❌ (4,096 필요) |
| Quality | ~1,500 tokens | Opus 4.5 | ❌ (4,096 필요) |
| Accuracy | ~1,500 tokens | Opus 4.5 | ❌ (4,096 필요) |

> **Note**: 모든 에이전트가 Opus 4.5 사용 (품질 우선). 캐싱을 위해서는 시스템 프롬프트를 4,096+ 토큰으로 확장 필요

### 15.5 캐싱 최적화 전략

#### risk_profile을 System Prompt에 포함

```python
# src/tools/compliance_evaluator_tool.py

def _build_system_prompt(
    source_lang: str,
    target_lang: str,
    risk_profile: Optional[Dict[str, Any]] = None,  # 캐시 대상
    content_context: str = "FAQ"
) -> str:
    """
    risk_profile을 시스템 프롬프트에 포함하여 캐싱 최적화:
    - 같은 국가의 번역을 여러 개 처리할 때 시스템 프롬프트가 캐시됨
    - 금칙어/면책문구 목록이 매번 재전송되지 않음
    """
    base_prompt = load_prompt("compliance_evaluator", ...)

    risk_section = f"""
## Risk Profile
<risk_profile>
{json.dumps(risk_profile, indent=2)}
</risk_profile>
"""
    return base_prompt + risk_section
```

#### User Prompt 최소화

```python
def _build_user_message(source_text: str, translation: str) -> str:
    """User prompt는 매번 변경되는 내용만 포함"""
    return f"""
<source_text>{source_text}</source_text>
<translation>{translation}</translation>
"""
```

### 15.6 메트릭 확인

결과 JSON에서 캐싱 메트릭 확인:

```json
{
  "metrics": {
    "token_usage": {
      "input": 4325,
      "output": 2362,
      "cache_read": 2021,   // ✅ 캐시 히트
      "cache_write": 0
    }
  }
}
```

### 15.7 배치 처리 시 캐싱 효과

```
같은 국가(US) 번역 100개 처리:

Request 1: System(1,800 + risk_profile) → cache_write
Request 2-100: System(cache_read) → 90% 비용 절감

예상 절감:
- 일반: 1,800 tokens × 100 = 180,000 tokens
- 캐싱: 1,800 + (1,800 × 0.1 × 99) = 19,620 tokens
- 절감: ~89%
```

### 15.8 설정 파일

`config/models.yaml`에서 캐싱 설정:

```yaml
caching:
  prompt_cache_enabled: true
  cache_type: "default"  # default (영구) | ephemeral (5분)
```

### 15.9 참고 자료

- [AWS Bedrock Prompt Caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html)

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| 1.0 | 2025-01-03 | 초안 작성 |
| 1.1 | 2026-01-05 | 용어집/스타일 가이드 자동 로드, --debug 옵션 추가 |
| 1.2 | 2026-01-05 | 프롬프트 캐싱 문서 추가 |
| 1.3 | 2026-01-05 | 모든 에이전트 Opus 4.5로 통일 (품질 우선) |
