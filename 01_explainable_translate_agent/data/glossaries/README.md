# 용어집 (Glossaries)

도메인/제품별 용어집을 관리합니다. 번역 시 일관성을 보장합니다.

## 왜 Glossary인가?

| 문제 | 영향 |
|------|------|
| **용어 불일치** | 같은 단어가 문서마다 다르게 번역됨 → 브랜드 혼란 |
| **번역자마다 다른 용어** | "sync"를 "동기화", "싱크", "연동" 등 다양하게 번역 |
| **에이전트 간 충돌** | Quality 에이전트가 Translator의 용어집 용어를 "어색하다"고 감점 |

**Glossary 해결책:**

| 기능 | 효과 |
|------|------|
| **용어 매핑 파일** | `source term → target term` 명시적 정의 |
| **제품별 분리** | abc_cloud, xyz_app 등 제품마다 별도 용어집 |
| **언어별 분리** | en.yaml, ja.yaml 등 타겟 언어별 용어 |
| **에이전트 공유** | Translator, Accuracy, Quality가 동일 용어집 참조 |

---

## 파일 구조

```
data/glossaries/
├── README.md              # 이 문서
└── abc_cloud/             # 제품별 디렉토리
    ├── en.yaml            # 영어 용어집
    ├── ja.yaml            # 일본어 용어집 (예시)
    └── zh-CN.yaml         # 중국어 용어집 (예시)
```

---

## 용어집 형식

```yaml
# {product}/{lang}.yaml
# Korean → Target Language 매핑

# 제품명
ABC 클라우드: ABC Cloud

# 핵심 기능
동기화: sync
백업: backup
복원: restore

# UI 요소
설정: Settings
앱: app

# 지원/서비스
고객센터: Customer Support
```

---

## 사용법

### 코드에서 로드

```python
from src.utils import get_glossary

# 제품 + 타겟 언어로 로드
glossary = get_glossary("abc_cloud", "en-rUS")
# Returns: {"ABC 클라우드": "ABC Cloud", "동기화": "sync", ...}

# 언어 fallback: en-rUS.yaml 없으면 en.yaml 사용
glossary = get_glossary("abc_cloud", "en-rGB")
# en-rGB.yaml 없으면 → en.yaml 로드
```

### TranslationUnit에서 사용

```python
from src.models import TranslationUnit
from src.utils import get_glossary

# 파일에서 용어집 로드
glossary = get_glossary("abc_cloud", "en-rUS")

unit = TranslationUnit(
    key="IDS_FAQ_001",
    source_text="ABC 클라우드에서 동기화가 되지 않습니다.",
    target_lang="en-rUS",
    glossary=glossary,  # 로드된 용어집 사용
    product="abc_cloud"
)
```

---

## 새 용어집 추가 방법

### 1. 새 제품 용어집

```bash
mkdir -p data/glossaries/new_product
touch data/glossaries/new_product/en.yaml
```

### 2. 새 언어 용어집

```bash
# 기존 영어 용어집 복사 후 번역
cp data/glossaries/abc_cloud/en.yaml data/glossaries/abc_cloud/ja.yaml
# ja.yaml 내용을 일본어로 수정
```

---

## Glossary-Aware Quality

Quality 에이전트에 Glossary를 전달하면 **에이전트 간 충돌을 방지**합니다:

```python
# Quality 에이전트가 용어집 제약 인식
quality_result = await evaluate_quality(
    source_text=source,
    translation=translation,
    glossary=glossary,  # 용어집 전달
    content_type="FAQ"
)

# "Customer Support"가 자연스럽지 않아도
# 용어집에 정의된 용어이므로 감점하지 않음
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/utils/config.py` | `get_glossary()` 함수 |
| `src/tools/translator_tool.py` | 번역 시 용어집 적용 |
| `src/tools/accuracy_evaluator_tool.py` | 용어집 준수 검사 |
| `src/tools/quality_evaluator_tool.py` | Glossary-Aware 평가 |
| `src/prompts/translator.md` | 번역 프롬프트 (용어집 섹션) |
