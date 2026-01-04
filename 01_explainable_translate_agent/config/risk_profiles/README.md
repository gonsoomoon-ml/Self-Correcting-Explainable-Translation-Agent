# 리스크 프로파일 (Risk Profiles)

국가별 규제 및 컴플라이언스 규칙을 정의하여 번역 품질을 관리합니다.

## 목적

리스크 프로파일은 각 타겟 시장에서 **금지되는 콘텐츠**, **필수 면책조항**, **톤/스타일 가이드**를 정의합니다. Compliance Evaluator 에이전트가 이 프로파일을 사용하여 번역을 평가합니다.

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
   cp US.yaml NEW_COUNTRY.yaml
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

| 프로파일 | 국가 | 지역 | 엄격도 | 주요 규제 |
|----------|------|------|--------|-----------|
| `US.yaml` | 미국 | 북미 | High | FTC, FDA, CCPA, COPPA, ADA |
| `DEFAULT.yaml` | (기본값) | 글로벌 | Medium | 기본 콘텐츠 안전 규칙 |

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

# 타겟 시장의 프로파일 로드
profile = get_risk_profile("US")

# 금칙어 접근
for term in profile["prohibited_terms"]:
    if term["pattern"] in translation:
        # 심각도에 따라 문제 플래그
        ...
```
