# 데이터 (Data)

번역 에이전트가 사용하는 참조 지식과 입출력 데이터를 관리합니다.

> **Note**: `source/`와 `output/` 폴더는 `.gitignore`에 포함됩니다 (독점 데이터).
> 테스트에는 `examples/` 폴더의 샘플 데이터를 사용하세요.

## 폴더 구조

```
data/
├── README.md
├── glossaries/       # 도메인별 용어집 (에이전트 참조 지식)
│   └── abc_cloud/    # ABC Cloud 용어집 (예시)
├── risk_profiles/    # 국가별 규제 규칙 (에이전트 참조 지식)
│   ├── US.yaml       # 미국 규제 (FTC, CCPA, COPPA)
│   └── DEFAULT.yaml  # 기본 규칙
├── source/           # 소스 데이터 - .gitignore (비공개)
│   └── ko_faq.json
└── output/           # 번역 결과물 - .gitignore (비공개)
    └── {lang}_faq.json
```

## 폴더별 설명

### source/ (비공개)

번역할 원본 FAQ (Korean). `.gitignore`에 포함.

```json
{
  "IDS_FAQ_SC_ABOUT": "ABC 클라우드는 ...",
  "IDS_FAQ_SC_SYNC": "동기화란 ..."
}
```

### glossaries/

도메인별 용어집. 번역 시 일관성 보장. Translator, Accuracy, Quality 에이전트가 사용.

```json
{
  "ABC 클라우드": "ABC Cloud",
  "ABC 계정": "ABC account",
  "동기화": "sync",
  "백업": "backup"
}
```

### risk_profiles/

국가별 규제 규칙. Compliance 에이전트가 사용.

```yaml
# US.yaml 예시
prohibited_terms:
  - pattern: "guaranteed"
    severity: high
required_disclaimers:
  data_backup:
    trigger_phrases: ["backup", "restore"]
    disclaimer: "Backup may not include all content."
```

> 상세 설명: [risk_profiles/README.md](risk_profiles/README.md)

### output/ (비공개)

번역 완료된 FAQ. 언어 코드별 파일. `.gitignore`에 포함.

| 파일 | 언어 |
|------|------|
| `en_faq.json` | English (US) |
| `en-rGB_faq.json` | English (UK) |

## 테스트 데이터

개발/테스트용 샘플 데이터는 `examples/` 폴더를 사용하세요:

```
examples/
├── single/           # 단일 항목 테스트
│   ├── faq.json
│   ├── ui.json
│   └── legal.json
└── batch/            # 배치 테스트
    ├── faq.json
    └── mixed.json
```
