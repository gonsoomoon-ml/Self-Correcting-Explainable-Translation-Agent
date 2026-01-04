# 요구사항 매핑

원본 요구사항과 현재 구현 상태를 비교합니다.

## End-to-End 흐름

### 원본 요구사항 (8단계)

```
1. 입력 & 메타 수집
   ↓
2. 사전 처리 (문장분할, placeholder 보호, PII 마스킹)
   ↓
3. 번역 후보 생성 (1~2개)
   ↓
4. 역번역 컨텍스트
   ↓
5. 다중 에이전트 평가 (7개 병렬)
   ↓
6. 의사결정 (Pass/Regen/HITL/Block)
   ↓
7. 발행 (UI 버튼 연동)
   ↓
8. 모니터링/로그 (S3/DynamoDB/QuickSight)
```

### 현재 구현

| 단계 | 원본 요구사항 | 현재 구현 | 상태 |
|------|--------------|----------|------|
| 1 | 원문, 언어쌍, 용어집, 스타일가이드, 리스크 프로파일 | `TranslationUnit` 모델 | ✅ 완료 |
| 2 | 문장분할, placeholder 보호, PII 마스킹 | 미구현 | ❌ TODO |
| 3 | 1~2개 후보 생성 | `num_candidates` 옵션 | ✅ 완료 |
| 4 | 역번역으로 의미 일치 확인 | `backtranslate_node` | ✅ 완료 |
| 5 | 7개 에이전트 병렬 평가 | 3개 에이전트로 통합 | ⚠️ 축소 |
| 6 | Pass/Regen/HITL/Block 판정 | `EvaluationGateSOP` | ✅ 완료 |
| 7 | UI 버튼 연동, GitHub 반영 | CLI만 지원 | ❌ TODO |
| 8 | S3/DynamoDB 저장, QuickSight 대시보드 | OTEL/CloudWatch만 | ⚠️ 부분 |

---

## 에이전트 매핑

### 원본 요구사항 (7개 에이전트)

| # | 에이전트 | 역할 | 점수 기준 |
|---|---------|------|----------|
| 1 | 번역 충실도 & 의미 일치 | 원문 대비 의미 손실/추가/왜곡, 숫자·단위·날짜 보존 (역번역 활용) | 5: 완전일치, 4: 경미, 3: 일부 누락, ≤2: 사실오류 |
| 2 | 용어집/고유명사 & 포맷 무결성 | 용어집 매핑 준수, 브랜드명 정확도, placeholder/마크업 보존 | 5: 모두 정확, 4: 1건 경미, 3: 다수 미매핑, ≤2: 법적명칭 오기 |
| 3 | 법률·규제 리스크 | 국가별 규제 위반, 과도한 확약, 필수 면책문구 누락 | 5: 위반없음, 4: 경미 조정, 3: 리스크 다수, ≤2: 명시적 위반 |
| 4 | 콘텐츠 안전성/비속어 | 비속어, 차별, 성적/폭력, 증오 발언 필터링 | 5: 안전, 4: 경계 1건, 3: 경계 다수, ≤2: 명백한 유해 |
| 5 | 문화/톤 & 브랜드 보이스 | 존대/격식, 지역 문화 금기, 브랜드 톤 일관성 | 5: 적합, 4: 경미 조정, 3: 오독 가능성, ≤2: 문화적 모욕 |
| 6 | A/B 번역 비교 | 후보간 유창성·가독성 비교, 최고 후보 선택 | 5: 명확한 우위, 4: 근소 차이, 3: 재생성 필요, ≤2: 모두 Fail |
| 7 | 출시 가드 (메타 에이전트) | 점수 집계, Pass/Fail 게이트, 재생성/에스컬레이션 정책 | 전원 ≥4 → Pass, 0~2 → Fail, 3 → 재생성 후 HITL |

### 현재 구현 (3개 에이전트 + 1 SOP)

```
┌─────────────────────────────────────────────────────────────────┐
│                    원본 7개 에이전트                              │
├─────────────────────────────────────────────────────────────────┤
│  1. 번역 충실도    2. 용어집/포맷  │  3. 법률규제   4. 콘텐츠안전  │  5. 문화/톤   6. A/B비교  │  7. 출시가드  │
└────────────┬──────────────────────┴───────────┬─────────────────┴──────────┬──────────────┴──────┬──────┘
             ↓                                   ↓                            ↓                     ↓
┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────┐
│   Accuracy Agent       │  │   Compliance Agent     │  │   Quality Agent        │  │  EvaluationGateSOP │
│   (Opus 4.5)           │  │   (Opus 4.5)           │  │   (Opus 4.5)           │  │  (Python 로직)      │
├────────────────────────┤  ├────────────────────────┤  ├────────────────────────┤  ├────────────────────┤
│ • 의미 보존 검증       │  │ • 금칙어 검사          │  │ • 유창성 평가          │  │ • 점수 집계         │
│ • 역번역 비교          │  │ • 필수 고지사항        │  │ • 톤/격식 적합성       │  │ • Pass/Fail 판정    │
│ • 용어집 매핑 확인     │  │ • 콘텐츠 안전성        │  │ • 문화적 적절성        │  │ • 재생성 정책       │
│ • 포맷 무결성          │  │ • 규제 정합성 (GDPR등) │  │ • A/B 후보 비교        │  │ • HITL 에스컬레이션 │
└────────────────────────┘  └────────────────────────┘  └────────────────────────┘  └────────────────────┘
```

### 통합 상세

| 현재 에이전트 | 통합된 원본 에이전트 | 프롬프트 위치 |
|--------------|---------------------|--------------|
| **Accuracy** | #1 번역 충실도 + #2 용어집/포맷 | [accuracy_evaluator.md](../src/prompts/accuracy_evaluator.md) |
| **Compliance** | #3 법률규제 + #4 콘텐츠안전 | [compliance_evaluator.md](../src/prompts/compliance_evaluator.md) |
| **Quality** | #5 문화/톤 + #6 A/B비교 | [quality_evaluator.md](../src/prompts/quality_evaluator.md) |
| **EvaluationGateSOP** | #7 출시가드 | [evaluation_gate.py](../sops/evaluation_gate.py) |

---

## 점수 체계

### 공통 스케일 (0-5)

| 점수 | 의미 | 액션 |
|------|------|------|
| **5** | 완벽 | Auto-Pass (발행 가능) |
| **4** | 경미한 수정으로 자동 치유 가능 | Auto-Pass |
| **3** | 경계/인간 검수 필요 | Regenerate 1회 → HITL |
| **0-2** | Fail | 즉시 차단 |

### 현재 구현 임계값

```python
# sops/evaluation_gate.py
class EvaluationGateConfig:
    pass_threshold: int = 5       # 모든 에이전트 5점 필요
    fail_threshold: int = 2       # 차단 최대 점수
    max_regenerations: int = 1    # 최대 재시도 횟수
    disagreement_threshold: int = 3  # 에이전트 불일치 임계값
```

---

## 데이터 흐름

### 입력 스키마 (TranslationUnit)

```json
{
  "key": "IDS_FAQ_001",
  "source_text": "원문 텍스트",
  "source_lang": "ko",
  "target_lang": "en-rUS",
  "glossary": {"용어": "term"},
  "style_guide": {"tone": "professional"},
  "risk_profile": "US",
  "product": "abc_cloud"
}
```

### 출력 스키마 (결과 JSON)

```json
{
  "key": "IDS_FAQ_001",
  "translation": "번역 결과",
  "workflow_state": "published|pending_review|rejected",
  "attempt_count": 2,
  "scores": {"accuracy": 5, "compliance": 5, "quality": 5},
  "verdict": "pass|regenerate|escalate|block",
  "details": {
    "evaluations": [...],      // 각 에이전트 reasoning_chain
    "attempt_history": [...],  // 재생성 히스토리
    "metrics": {...}           // 비용, 토큰, 지연시간
  }
}
```

---

## 미구현 항목 (TODO)

### 높은 우선순위

| 항목 | 설명 | 관련 요구사항 |
|------|------|--------------|
| 사전처리 | 문장분할, placeholder 보호, PII 마스킹 | 단계 2 |
| UI 연동 | 발행 버튼, 수정안 수락/적용 | 단계 7 |

### 중간 우선순위

| 항목 | 설명 | 관련 요구사항 |
|------|------|--------------|
| 영구 저장소 | S3 + DynamoDB 저장 | 단계 8 |
| 대시보드 | QuickSight 연동 (실패율, 평균 점수 추세) | 단계 8 |
| Bedrock Guardrails | 네이티브 거버넌스 템플릿 연계 | 에이전트 #4 |

### 낮은 우선순위

| 항목 | 설명 | 관련 요구사항 |
|------|------|--------------|
| 에이전트 분리 | 3개 → 7개 세분화 (필요시) | 원본 설계 |
| 버전 관리 | 용어집/스타일가이드 버전 ID 주입 | 데이터 가드라인 |

---

## 참고 문서

- [IMPLEMENTATION_GUIDE.md](../IMPLEMENTATION_GUIDE.md) - 상세 구현 가이드
- [observability.md](./observability.md) - OTEL/CloudWatch 설정
- [config/README.md](../config/README.md) - 설정 파일 가이드
