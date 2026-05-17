# 리스크 프로파일 (Risk Profiles)

국가별 규제 및 컴플라이언스 규칙을 정의하여 번역 품질을 관리합니다.

## 왜 Risk Profile인가?

| 문제 | 영향 |
|------|------|
| **국가별 규제 차이** | 미국 FTC vs EU GDPR vs 중국 PIPL - 동일 번역이 한 국가에서는 합법, 다른 국가에서는 위법 |
| **금칙어 관리 어려움** | "guaranteed", "100% safe" 등 마케팅 문구가 법적 문제 야기 |
| **면책조항 누락** | 데이터 백업, 결제 관련 필수 고지 누락 시 법적 위험 |
| **일관성 없는 검토** | 검수자마다 다른 규제 지식 → 품질 편차 |

**Risk Profile 해결책:**

| 특성 | 효과 |
|------|------|
| **YAML로 규칙 외부화** | 코드 수정 없이 규제 업데이트 |
| **국가별 프로파일 분리** | US, EU, CN 등 각 시장에 맞는 규칙 적용 |
| **심각도 수준 정의** | low → critical까지 자동 점수 조정 |
| **Compliance Agent 연동** | 규칙 기반 자동 검사 + 수정 제안 |

---

## 아키텍처에서의 위치

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              번역 파이프라인                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────┐                                                         │
│  │  RISK PROFILE   │                                                         │
│  │   (US.yaml)     │                                                         │
│  ├─────────────────┤                                                         │
│  │ • 금칙어        │                                                         │
│  │ • 면책조항      │──────────────────────┐                                   │
│  │ • 개인정보 규칙 │                      │                                   │
│  │ • 톤/격식       │                      │                                   │
│  └─────────────────┘                      ▼                                   │
│                               ┌─────────────────────┐                        │
│                    ┌──────────│  EVALUATE (3 병렬)  │──────────┐              │
│                    │          └─────────────────────┘          │              │
│                    ▼                    ▼                      ▼              │
│             ┌───────────┐        ┌───────────┐          ┌───────────┐        │
│             │ Accuracy  │        │Compliance │◀─────────│  Quality  │        │
│             │ Evaluator │        │ Evaluator │ Risk     │ Evaluator │        │
│             │           │        │           │ Profile  │           │        │
│             └───────────┘        └───────────┘ 적용     └───────────┘        │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 파일 구조

```
data/risk_profiles/
├── README.md                  # 이 문서
├── abc_cloud/                 # 제품별 디렉토리 (SaaS)
│   ├── DEFAULT.yaml           # 글로벌 SaaS baseline
│   └── US.yaml                # 미국 시장 (FTC, CCPA, COPPA, ADA)
└── finance_kr/                # 제품별 디렉토리 (금융)
    └── KR.yaml                # 한국 금융 (자본시장법·금소법·예금자보호법·PIPA)
```

> Strict 로딩: `{product}/{country_code}.yaml` 정확 일치 파일만 로드됩니다. 누락 시 `FileNotFoundError`.

---

## 동작 방식

```
US 시장용 번역
        ↓
Compliance Agent가 US.yaml 로드
        ↓
검사: 금칙어, 필수 면책조항, 개인정보 규칙
        ↓
반환: 점수 (0-5), 발견된 문제, 수정 제안
```

### 검사 예시

| 번역 | 위반 | 심각도 | 점수 영향 |
|------|------|--------|-----------|
| "This is **guaranteed** to work" | 절대적 보증 주장 (FTC) | high | -2 |
| "**100% safe** for your data" | 안전성 절대 주장 (FDA) | critical | 차단 |
| "Back up your data" (면책조항 없음) | 면책조항 누락 | medium | -1 |

## 스키마 레퍼런스

```yaml
# 프로파일 메타데이터
profile:
  country_code: US                    # ISO 국가 코드
  country_name: United States         # 표시 이름
  region: North America               # 지역
  regulatory_strictness: high         # low | medium | high

# 번역에 포함되면 안 되는 용어
prohibited_terms:
  - pattern: "guaranteed"             # 매칭할 텍스트 패턴
    context: "absolute claims"        # 금지 이유
    severity: high                    # low | medium | high | critical
    suggestion: "완화된 표현 사용"      # 수정 방법

# 특정 문구가 있을 때 반드시 추가해야 하는 면책조항
required_disclaimers:
  data_backup:                        # 면책조항 카테고리
    trigger_phrases:                  # 트리거 문구 목록
      - "backup"
      - "restore"
    disclaimer: "데이터 백업에 모든 콘텐츠가 포함되지 않을 수 있습니다."
    placement: "near_content"         # near_content | before_action | footer

# 개인정보 보호 규칙
privacy:
  pii_categories:
    - name: "personal_data"
      handling: "must_disclose_collection"  # 처리 요구사항
  consent_requirements:
    - type: "data_collection"
      timing: "before_collection"

# 연령 제한 (예: COPPA)
age_restrictions:
  coppa:
    applies_to_under: 13
    requirements:
      - "parental_consent_required"

# 접근성 요구사항 (예: ADA)
accessibility:
  requirements:
    - "alt_text_for_images"
    - "screen_reader_compatible"

# 톤과 격식 가이드라인
tone:
  formality_level: medium             # low | medium | high
  avoid:
    - "overly casual language"
  prefer:
    - "clear and direct"
```

## 새 프로파일 추가 방법

1. 기존 프로파일을 템플릿으로 복사:
   ```bash
   # 같은 제품, 다른 국가
   cp abc_cloud/US.yaml abc_cloud/NEW_COUNTRY.yaml

   # 다른 제품, 같은 국가
   cp finance_kr/KR.yaml new_product/KR.yaml
   ```

2. `profile` 섹션에 올바른 국가 정보 입력

3. 국가별 규제 조사 후 추가:
   - 금칙어 (광고법, 건강 관련 주장 등)
   - 필수 면책조항 (소비자 보호법)
   - 개인정보 규칙 (EU는 GDPR, 중국은 PIPL 등)
   - 연령 제한
   - 접근성 요구사항
   - 톤 선호도

4. Compliance Evaluator 에이전트로 테스트

## 사용 가능한 프로파일

| 경로 | 제품 | 국가 | 엄격도 | 주요 규제 |
|------|------|------|--------|-----------|
| `abc_cloud/DEFAULT.yaml` | abc_cloud (SaaS) | 글로벌 | Medium | 기본 콘텐츠 안전 규칙 |
| `abc_cloud/US.yaml` | abc_cloud (SaaS) | 미국 | High | FTC, FDA, CCPA, COPPA, ADA |
| `finance_kr/KR.yaml` | finance_kr (금융) | 한국 | High | 자본시장법, 금소법, 예금자보호법, PIPA |

### US.yaml 요약

| 카테고리 | 규칙 수 | 주요 내용 |
|----------|---------|-----------|
| **prohibited_terms** | 9개 | guaranteed, 100% safe, cures, risk-free 등 |
| **required_disclaimers** | 4개 | data_backup, cloud_storage, account_deletion, payment |
| **privacy** | 3개 | personal_data, location_data, biometric_data |
| **age_restrictions** | 1개 | COPPA (13세 미만) |
| **accessibility** | 3개 | alt_text, screen_reader, color_contrast |
| **tone** | medium | clear and direct, professional |

## 심각도 수준

| 수준 | 점수 영향 | 조치 |
|------|-----------|------|
| `low` | -0.5 | 경고만 표시 |
| `medium` | -1 | 수정 권장 |
| `high` | -2 | 반드시 수정 |
| `critical` | 차단 (점수 ≤2) | 발행 불가 |

## 코드에서 사용법

```python
from src.utils import get_risk_profile

# 제품 + 타겟 시장 프로파일 로드 (strict — 정확 일치만)
profile = get_risk_profile("abc_cloud", "US")   # → abc_cloud/US.yaml
profile = get_risk_profile("finance_kr", "KR")  # → finance_kr/KR.yaml

# 금칙어 접근
for term in profile["prohibited_terms"]:
    if term["pattern"] in translation:
        # 심각도에 따라 문제 플래그
        ...
```

---

## Compliance Agent 출력 예시

Risk Profile 위반 시 Compliance Agent가 반환하는 결과:

```json
{
  "agent_name": "compliance",
  "reasoning_chain": [
    "Step 1: 금칙어 검사 - 'guaranteed' 발견 (FTC 위반)",
    "Step 2: 면책조항 검사 - 'backup' 언급 시 면책조항 필요하나 누락",
    "Step 3: 개인정보 규칙 검사 - 통과",
    "Step 4: 최종 판단 - 2개 위반 발견, 점수 3점"
  ],
  "score": 3,
  "verdict": "regenerate",
  "issues": [
    "금칙어 'guaranteed' 사용 (severity: high)",
    "데이터 백업 면책조항 누락 (severity: medium)"
  ],
  "corrections": [
    {
      "original": "This is guaranteed to work",
      "suggested": "This is designed to work reliably",
      "reason": "FTC 규정상 절대적 보증 주장 금지"
    },
    {
      "original": "Back up your data",
      "suggested": "Back up your data. Note: Backup may not include all content.",
      "reason": "US.yaml required_disclaimers.data_backup"
    }
  ],
  "risk_flags": [
    {"type": "prohibited_term", "term": "guaranteed", "severity": "high"},
    {"type": "missing_disclaimer", "category": "data_backup", "severity": "medium"}
  ]
}
```

---

## 향후 확장 계획

| 프로파일 | 국가 | 주요 규제 | 상태 |
|----------|------|-----------|------|
| `EU.yaml` | 유럽연합 | GDPR, DSA, AI Act | 🔮 계획 |
| `CN.yaml` | 중국 | PIPL, CSL | 🔮 계획 |
| `JP.yaml` | 일본 | APPI, JIS | 🔮 계획 |
| `KR.yaml` | 한국 | PIPA, 정보통신망법 | 🔮 계획 |

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/tools/compliance_evaluator_tool.py` | Risk Profile을 사용하는 Compliance 에이전트 |
| `src/prompts/compliance_evaluator.md` | Compliance 에이전트 프롬프트 ({{ risk_profile }} 변수) |
| `src/models/agent_result.py` | `risk_flags` 필드 정의 |
| `config/settings.yaml` | 기본 Risk Profile 설정 |
