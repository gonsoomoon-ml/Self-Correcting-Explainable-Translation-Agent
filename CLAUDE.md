# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**All documentation should be in Korean, NOT English.**

## Project Overview

AWS Bedrock 기반 다국어 FAQ 자동 번역 시스템. 에이전트 기반 가드레일로 품질/리스크 관리.

## Common Commands

```bash
# Environment setup (필수, 최초 1회)
./setup/create_env.sh

# AWS 인증 (필수)
aws configure

# 워크플로우 실행 (01_explainable_translate_agent/ 디렉토리에서)
uv run --no-sync python test_workflow.py              # 단일 테스트
uv run --no-sync python test_workflow.py --dry-run    # 구조 확인 (API 호출 없음)
uv run --no-sync python test_workflow.py --debug      # 디버그 모드 (프롬프트 출력)

# 옵션
--input <file>          # 입력 JSON 파일
--session-id <id>       # 커스텀 세션 ID
--max-regen <n>         # 최대 재생성 횟수 (기본: 1)
```

## Architecture

### Workflow Pipeline
```
INPUT → TRANSLATE → BACKTRANSLATE → EVALUATE (3 agents 병렬) → GATE
                                                                 ↓
                                            ┌────────────────────┼────────────────────┐
                                            ↓                    ↓                    ↓
                                        PUBLISHED           REGENERATE            REJECTED
                                                          (loop back)             /BLOCK
```

### Key Layers

| Layer | Location | Description |
|-------|----------|-------------|
| **Models** | `src/models/` | Pydantic 데이터 모델 (TranslationUnit, AgentResult, GateDecision) |
| **Tools** | `src/tools/` | Agent-as-Tool 래퍼 - Bedrock 호출 |
| **SOPs** | `sops/` | 의사결정 절차 (EvaluationGateSOP, RegenerationSOP) |
| **Graph** | `src/graph/` | Strands GraphBuilder 워크플로우 오케스트레이션 |
| **Skills** | `skills/` | 재사용 가능한 지식/프롬프트 패키지 (SKILL.md + references/) |

### 3 Evaluation Agents

| Agent | 평가 영역 |
|-------|-----------|
| ACCURACY | 의미 보존, 역번역 검증, 용어 매핑, 포맷 무결성 |
| COMPLIANCE | 규제 준수, 금칙어, 면책문구, 콘텐츠 안전 |
| QUALITY | 톤/격식, 문화 적합성, 후보 비교 |

### Scoring (0-5 Scale)

| Score | Action |
|-------|--------|
| 5 | Pass (자동 발행) |
| 3-4 | Regenerate (피드백 반영 재생성) → 최대 횟수 초과 시 Rejected |
| ≤2 | Block (즉시 거부) |

## Key Files

- `test_workflow.py` - 워크플로우 테스트 진입점
- `src/graph/builder.py` - TranslationWorkflowGraphV2 클래스 (Strands GraphBuilder)
- `src/graph/nodes.py` - 파이프라인 노드 (translate, backtranslate, evaluate, decide)
- `sops/evaluation_gate.py` - EvaluationGateSOP (Pass/Block/Regenerate/Rejected 판정)
- `src/utils/observability.py` - OTEL 트레이싱 유틸리티

## Bedrock Integration

- Region: `us-west-2`
- Model: Claude Opus 4.5 (`global.anthropic.claude-opus-4-5-20251101-v1:0`)
- API: boto3 Bedrock Converse API

## Observability (OTEL)

CloudWatch GenAI Observability 연동. 자세한 내용: `01_explainable_translate_agent/docs/observability.md`

```python
# OTEL 세션으로 워크플로우 실행
with observability_session(session_id="user-123", workflow_name="translation"):
    result = await graph.run(unit)
```

## Results

결과는 `01_explainable_translate_agent/results/` 에 JSON으로 저장:
- `results/single/<timestamp>/<key>.json` - 단일 테스트 결과
