# Self-Correcting Explainable Translation Agent

3개 평가 에이전트가 품질을 검증하고, 피드백 기반으로 스스로 개선하여 사람의 검수를 돕는 LLM 번역 시스템

> 평가하고, 설명하고, 스스로 개선한다.

## 일반적인 번역 작업의 문제 (Why?)
일반적으로 번역의 업무는 사람에 크게 의존을 하고 있습니다. 아래와 같은 일반적인 문제를 가지고 있습니다.

| 기존 워크플로우 문제 | 영향 |
|---------------------|------|
| 수동 검수 병목 | 사람이 모든 번역을 검토 → 출시 지연 |
| 일관성 없는 품질 | 검수자마다 다른 기준 적용 |
| 용어 불일치 | 같은 단어가 문서마다 다르게 번역 → 브랜드 혼란 |
| 블랙박스 판정 | "왜 리젝?" 설명 부재 |
| 비결정적 의사결정 | LLM 출력이 매번 달라 감사 불가 |
| 규정 준수 리스크 | 금칙어·면책문구 누락 → 법적 위험 |

## 만들고자 하는 것 (What?)

**목표**: 고품질 번역을 자동 검증하고 개선하여 사람의 검수 부담을 줄이는 시스템

| 문제 | 해결책 | 구현 방식 |
|------|--------|----------|
| 수동 검수 병목 | 자동 품질 관리 | 3개 에이전트가 정확성/규정준수/품질 병렬 평가 |
| 블랙박스 판정 | 설명 가능한 판정 | 모든 점수에 Chain-of-Thought 근거 제시 |
| 일관성 없는 품질 | 자동 품질 개선 | Maker-Checker 패턴으로 피드백 기반 재생성 |
| 용어 불일치 | 용어집 기반 번역 | 도메인별 Glossary로 용어 일관성 강제 |
| 비결정적 의사결정 | SOP 기반 정책 | 판정 로직을 Python 코드로 명확히 정의 (LLM 호출 없음) |
| 규정 준수 리스크 | 투명한 의사결정 | 검수자가 판정 근거를 즉시 확인 가능 |

### Technical Novelty

| 기술 | 혁신점 |
|------|--------|
| **Multi-Agent Evaluation** | 단일 LLM 대신 3개 전문 에이전트가 각자 영역 평가 → 높은 정밀도 |
| **Backtranslation Verification** | 역번역으로 의미 보존 검증 → 환각(hallucination) 감지 |
| **Maker-Checker Loop** | 평가 에이전트 피드백을 번역 에이전트에 주입 → 자동 개선 |
| **Explainable Scoring** | 0-5 점수 + reasoning_chain → 감사 가능한 판정 |
| **SOP-Driven Policy** | 판정 로직(Pass/Block/Regenerate)을 Python SOP로 분리 → LLM 비의존적, 결정론적, 감사 가능 |
| **Glossary-Aware Quality** | Quality 에이전트가 용어집 제약 인식 → "Customer Support"가 어색해도 규정 용어면 감점 안함 |

## 어떻게 만드나 (How?)

5단계 파이프라인으로 번역을 생성하고 검증합니다. 용어집(Glossary)이 전체 파이프라인에 용어 제약을 주입하고, SOP가 결정론적 정책을 적용합니다.

| 단계 | 노드 | 역할 |
|------|------|------|
| [1] 번역 | TRANSLATE | 원문 → 대상 언어 번역 (용어집 적용) |
| [2] 역번역 | BACKTRANSLATE | 번역 → 원본 언어로 재번역 (의미 보존 검증용) |
| [3] 평가 | EVALUATE | 3개 에이전트가 병렬로 품질 평가 |
| [4] 판정 | DECIDE | SOP가 점수 기반으로 Pass/Regenerate/Block 결정 |
| [5] 최종 | FINALIZE | 판정에 따라 발행/거부/검수대기 처리 |

```
                              ┌──────────┐
                              │ GLOSSARY │ (용어 제약)
                              └────┬─────┘
                                   │
┌──────────────────────────────────┼──────────────────────────────────────────┐
│                              번역 파이프라인                                  │
└──────────────────────────────────┼──────────────────────────────────────────┘
                                   ▼
    [1] 번역        [2] 역번역       [3] 평가         [4] 판정        [5] 최종
   ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
   │TRANSLATE────▶│  BACK  │────▶│EVALUATE│────▶│ DECIDE │────▶│FINALIZE│
   │        │     │TRANSLATE     │        │     │        │     │        │
   └────────┘     └────────┘     └────────┘     └────────┘     └────────┘
       ▲                              │              │              │
       │                              │              ▼              ▼
       │                         ┌────┴────┐   ┌─────────┐    ┌─────────┐
       │                         │ 3 Agent │   │   SOP   │    │ ✅ 발행 │
       │                         │ 병렬실행 │   │ (정책)  │    │ ❌ 거부 │
       │                         └─────────┘   └────┬────┘    │ 🔍 검수 │
       │                                            │         └─────────┘
       └────────────────────────────────────────────┘
                        (Maker-Checker 루프)
```

### 점수 체계 (0-5)

| 점수 | 판정 | 액션 |
|------|------|------|
| **5** | ✅ Pass | 자동 발행 |
| **3-4** | 🔄 Regenerate | 피드백 반영 재생성 → 5점 도달까지 반복 |
| **≤2** | ❌ Block | 즉시 거부 |

## Quick Start

```bash
# 1. 환경 설정 (최초 1회)
./setup/create_env.sh

# 2. AWS 인증
aws configure

# 3. 실행
cd 01_explainable_translate_agent

# 단일 테스트
uv run python test_workflow.py --input examples/single/faq.json --max-regen 2
uv run python test_workflow.py --input examples/single/ui.json --max-regen 2
uv run python test_workflow.py --input examples/single/legal.json --max-regen 2

# 배치 테스트
uv run python test_workflow.py --batch --input examples/batch/mixed.json
uv run python test_workflow.py --batch --input examples/batch/faq.json
```

### 실행 예시

```bash
$ uv run python test_workflow.py --input examples/single/ui.json --max-regen 2

============================================================
테스트: IDS_UI_REGEN_001
원문: 데이터 동기화 중 오류가 발생했습니다. 네트워크 연결을 확인하시고...
대상 언어: en-rUS
============================================================
워크플로우 시작: IDS_UI_REGEN_001
[IDS_UI_REGEN_001] 번역 완료: 1개 후보 (4150ms)
[IDS_UI_REGEN_001] 역번역 완료 (3953ms)
[IDS_UI_REGEN_001] 평가 완료: {'accuracy': 5, 'compliance': 5, 'quality': 4}
[IDS_UI_REGEN_001] 판정: regenerate
[IDS_UI_REGEN_001] 피드백: 1개 이슈, 1개 수정
[IDS_UI_REGEN_001] 번역 완료: 1개 후보 (3735ms)
[IDS_UI_REGEN_001] 역번역 완료 (3964ms)
[IDS_UI_REGEN_001] 평가 완료: {'accuracy': 5, 'compliance': 5, 'quality': 5}
[IDS_UI_REGEN_001] 판정: pass
[IDS_UI_REGEN_001] 발행 완료
워크플로우 완료: published (시도 2회, 36112ms)

✅ 워크플로우 완료 (36.1s)
├─ 번역: 3735ms
│   └─ An error occurred during data sync. Please check your network...
├─ 역번역: 3964ms
│   └─ 데이터 동기화 중 오류가 발생했습니다...
├─ 평가: 25374ms
│   ├─ accuracy: 5 ✓
│   ├─ compliance: 5 ✓
│   └─ quality: 5 ✓
└─ 판정 (2회 시도)
    ├─ [시도 1] regenerate (accuracy:5, compliance:5, quality:4)
    └─ [시도 2] pass (accuracy:5, compliance:5, quality:5)

💰 비용: $0.0564 | 토큰: 5,324+1,903
```

결과 파일: `results/single/<timestamp>/<key>.json`

## Example: Maker-Checker 자동 개선

아래는 실제 실행 예시입니다. 3회 시도 끝에 모든 에이전트가 만점을 부여했습니다.

**입력:**
```
데이터 동기화 중 오류가 발생했습니다. 네트워크 연결을 확인하시고,
문제가 지속되면 고객센터로 문의해 주세요. 자동 재시도는 5분 후에 진행됩니다.
```

**시도 1** → Quality: 4점 (재생성)
```
Issue: "'Automatic retry will proceed in 5 minutes'가 약간 형식적"
Correction: "proceed" → "occur" 제안
```

**시도 2** → Accuracy: 4점 (재생성)
```
Issue: "'진행됩니다'와 'will occur'의 뉘앙스 차이"
Correction: "will occur" → "will be initiated" 제안
```

**시도 3** → 모든 에이전트 5점 (발행)
```json
{
  "translation": "An error occurred during data sync. Please check your network
                  connection, and if the problem persists, contact Customer Support.
                  An automatic retry will be initiated in 5 minutes.",
  "scores": {"accuracy": 5, "compliance": 5, "quality": 5},
  "verdict": "pass",
  "attempt_count": 3,
  "cost_usd": 0.062
}
```

**평가 근거 (Chain-of-Thought):**
| 에이전트 | 평가 |
|----------|------|
| Accuracy | 의미 완벽 보존, 용어집 100% 준수 (sync, network, Customer Support, automatic retry) |
| Compliance | 금칙어 없음, 법적 고지 불필요, GDPR/CCPA 해당 없음 |
| Quality | 자연스러운 문장, FAQ에 적합한 톤, 문화적으로 적절 |

> 전체 결과: [examples/output_sample.json](01_explainable_translate_agent/examples/output_sample.json)

## Implementation Approach

본 시스템은 **관심사 분리 아키텍처**를 채택합니다.

### Core Architecture (4 Layers)

| 레이어 | 위치 | 역할 | 핵심 파일 |
|--------|------|------|-----------|
| **Graph** | `src/graph/` | 워크플로우 오케스트레이션 (State Machine) | `builder.py`, `nodes.py` |
| **Tools** | `src/tools/` | Agent-as-Tool 패턴으로 LLM 호출 캡슐화 | `translator`, `*_evaluator` (3개) |
| **SOPs** | `sops/` | 결정론적 정책 로직 (LLM 호출 없음) | `evaluation_gate`, `regeneration` |
| **Models** | `src/models/` | Pydantic 기반 타입 안전 데이터 구조 | `TranslationUnit`, `GateDecision` |

### Supporting Components

| 컴포넌트 | 위치 | 역할 |
|----------|------|------|
| **Prompts** | `src/prompts/` | 에이전트별 시스템 프롬프트 템플릿 (Markdown) |
| **Glossaries** | `data/glossaries/` | 도메인별 용어집 → 용어 일관성 강제 |
| **Config** | `config/` | 임계값, 모델, 언어 설정 (YAML) |
| **Utils** | `src/utils/` | Strands Agent 래퍼, OTEL 트레이싱 |

### 핵심 설계 결정

| 결정 | 이유 | 효과 |
|------|------|------|
| **SOP로 정책 분리** | 판정 로직을 Python 코드로 명확히 정의 | LLM 비의존적, 결정론적, 감사 가능 |
| **병렬 평가** | 3개 에이전트가 `asyncio.gather`로 동시 실행 | 지연시간 최소화 |
| **프롬프트/로직 분리** | Prompts(지식)는 Markdown, SOPs(판정)는 Python | 각각 독립 수정 가능 |
| **설정 외부화** | 임계값, 모델, 언어를 YAML로 관리 | 코드 수정 없이 튜닝 |
| **Glossary 공유** | 번역·평가 에이전트가 동일 용어집 참조 | 에이전트 간 충돌 방지 |

## Project Structure

```
explainable-translate-agent/
├── setup/                      # 환경 설정
│   └── create_env.sh
├── 01_explainable_translate_agent/
│   ├── src/
│   │   ├── graph/             # 워크플로우 State Machine
│   │   ├── models/            # Pydantic 데이터 모델
│   │   ├── tools/             # Agent-as-Tool 래퍼
│   │   └── prompts/           # 프롬프트 템플릿
│   ├── sops/                  # 의사결정 로직 (Gate, Regeneration)
│   ├── config/                # 설정 파일
│   ├── examples/              # 테스트 입력 예제
│   └── results/               # 실행 결과 (JSON)
├── CLAUDE.md                  # 개발 가이드
└── README.md                  # 이 문서
```

## Tech Stack

Python 3.11+ · AWS Bedrock · Claude 4.5 Opus · Strands Agents · OpenTelemetry

## Documentation

### 시작하기

| 문서 | 설명 |
|------|------|
| [setup/](setup/) | 환경 설정 스크립트 |

### 아키텍처

| 문서 | 설명 |
|------|------|
| [src/graph/README.md](01_explainable_translate_agent/src/graph/README.md) | 워크플로우 State Machine |
| [src/models/README.md](01_explainable_translate_agent/src/models/README.md) | 데이터 모델 (Pydantic) |
| [sops/README.md](01_explainable_translate_agent/sops/README.md) | 의사결정 절차 (Gate, Regeneration) |

### 에이전트 & 프롬프트

| 문서 | 설명 |
|------|------|
| [src/tools/README.md](01_explainable_translate_agent/src/tools/README.md) | Agent-as-Tool 래퍼 |
| [src/prompts/README.md](01_explainable_translate_agent/src/prompts/README.md) | 프롬프트 설계 가이드 |
| [skills/README.md](01_explainable_translate_agent/skills/README.md) | 재사용 가능 지식 패키지 |

### 설정

| 문서 | 설명 |
|------|------|
| [config/README.md](01_explainable_translate_agent/config/README.md) | YAML 설정 가이드 |

### 운영

| 문서 | 설명 |
|------|------|
| [docs/observability.md](01_explainable_translate_agent/docs/observability.md) | OTEL 트레이싱 설정 |
