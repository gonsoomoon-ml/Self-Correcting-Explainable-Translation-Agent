# CLAUDE.md

이 프로젝트에서 작업할 때의 *team conventions* 및 *Claude Code 동작 지침*.

## Language

답변은 **한국어 중심**, 기술 용어는 영어 병기 (e.g., "에이전트 (agent)",
"노드 (node)"). 코드 주석/식별자는 영어 유지.

## Workflow

작업 시 다음 cycle:

1. **탐색 / Plan Mode** (`Shift+Tab` 2회 또는 `/plan`) — 변경 전 *계획부터*
2. **사용자 승인** — Plan 검토 + Approve 후 진행
3. **구현** — Write tool, 한 번에 한 변경
4. **검증** — dry-run 또는 actual test

*큰 변경 (multi-file, architectural)* 시 *반드시 Plan Mode 사용*.

## Spec 우선 원칙 (Spec is primary)

**Declarative spec files (data, configs, rules, templates) 가
*시스템 행동의 ground truth***.

- 데이터 / config 파일이 *시스템 동작 결정*
- Code 는 spec 을 *serve* 하는 mechanism
- 새 도메인/규칙 추가 시 *spec 추가가 우선*, code 수정은 *마지막 수단*
- *Spec 변경 시 *도메인 전문가 review 필수* — AI 추측은 *imperfect*

## Code 변경 주의

- *Deterministic decision logic* (Python SOP, gate functions) — 변경 매우 신중
- *Workflow orchestrator* — multi-file 영향, Plan Mode 필수
- *Prompt templates* — 영향 광범위, 변경 후 *test 필수*

*Code 변경 시 *해당 spec 도 함께 검토**.

## Maker-Checker 패턴

AI 가 *generate* 한 산출물 (코드 / 데이터 / 응답) 은 *사람의 Reviewer 단계 통과 후 적용*:

- AI 의 첫 출력 = *후보 (candidate)*
- 사람의 검증 + 수정 = *ground truth*
- 검증 없이 *직접 적용 금지*

## Mindset

**한 사람의 3 역할** (AI 와 함께):

- **Architect** (Specify) — 의도를 spec 으로 외재화
- **Reviewer** (Verify) — spec / code / result 검증
- **Conductor** (Orchestrate) — workflow + 협업 흐름 조율

*Spec 이 primary, code 가 spec 을 serve.*
