# 스타일 가이드 (Style Guides)

제품/언어별 스타일 가이드를 관리합니다. 번역 시 톤과 스타일을 일관되게 유지합니다.

## 왜 Style Guide인가?

| 문제 | 영향 |
|------|------|
| **톤 불일치** | 같은 제품이 문서마다 다른 톤 → 브랜드 경험 저하 |
| **번역자마다 다른 스타일** | 공식적 vs 친근한 표현 혼재 |

**Style Guide 해결책:**

| 기능 | 효과 |
|------|------|
| **스타일 속성 정의** | tone, voice, formality 등 명시적 정의 |
| **제품별 분리** | abc_cloud, xyz_app 등 제품마다 별도 가이드 |
| **언어별 분리** | en.yaml, ja.yaml 등 타겟 언어별 스타일 |
| **자동 로드** | `product` + `target_lang`으로 자동 로드 |

---

## 파일 구조

```
data/style_guides/
├── README.md              # 이 문서
└── abc_cloud/             # 제품별 디렉토리
    ├── en.yaml            # 영어 스타일 가이드
    ├── ja.yaml            # 일본어 스타일 가이드 (예시)
    └── zh-CN.yaml         # 중국어 스타일 가이드 (예시)
```

---

## 스타일 가이드 형식

```yaml
# {product}/{lang}.yaml

# ABC Cloud 스타일 가이드 (English)
tone: formal
voice: active
formality: professional
sentence_style: concise
```

### 속성 설명

| 속성 | 값 예시 | 설명 |
|------|---------|------|
| `tone` | formal, casual, friendly | 전체적인 톤 |
| `voice` | active, passive | 능동태/수동태 선호 |
| `formality` | professional, casual | 격식 수준 |
| `sentence_style` | concise, elaborate | 문장 스타일 |

---

## 사용법

### 자동 로드

`translate_node`에서 `product`와 `target_lang`을 기반으로 **자동 로드**됩니다:

```python
# src/graph/nodes.py
from src.utils.config import get_style_guide

async def translate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    unit = state["unit"]

    # 자동 로드: data/style_guides/{product}/{lang}.yaml
    style_guide = get_style_guide(unit.product, unit.target_lang)
    # unit.product="abc_cloud", unit.target_lang="en-rUS" → en.yaml 로드

    result = await translate(
        source_text=unit.source_text,
        style_guide=style_guide,  # 자동 로드된 스타일 가이드
        ...
    )
```

### 언어 코드 Fallback

```python
# 언어 fallback: en-rUS.yaml 없으면 en.yaml 사용
style_guide = get_style_guide("abc_cloud", "en-rUS")
# en-rUS.yaml 없으면 → en.yaml 로드
```

---

## 새 스타일 가이드 추가 방법

### 1. 새 제품 스타일 가이드

```bash
mkdir -p data/style_guides/new_product
touch data/style_guides/new_product/en.yaml
```

### 2. 새 언어 스타일 가이드

```bash
# 기존 영어 스타일 가이드 복사 후 수정
cp data/style_guides/abc_cloud/en.yaml data/style_guides/abc_cloud/ja.yaml
# ja.yaml 내용을 일본어에 맞게 수정
```

---

## 프롬프트 주입

스타일 가이드는 시스템 프롬프트의 `<style_guide>` 섹션에 주입됩니다:

```markdown
## Style Guide
<style_guide>
- tone: formal
- voice: active
- formality: professional
- sentence_style: concise
</style_guide>
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `src/utils/config.py` | `get_style_guide()` 함수 |
| `src/graph/nodes.py` | 스타일 가이드 자동 로드 |
| `src/tools/translator_tool.py` | 프롬프트에 스타일 가이드 주입 |
| `src/prompts/translator.md` | 번역 프롬프트 템플릿 |
