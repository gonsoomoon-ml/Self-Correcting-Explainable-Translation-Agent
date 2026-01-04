"""
번역 파이프라인 도구 모음

Strands Agent 기반 번역 및 평가 도구들.
프롬프트 캐싱으로 시스템 프롬프트 비용 90% 절감.
모든 도구는 async로 구현되어 asyncio.gather()로 병렬 실행 가능.

도구 목록:
- translate: 번역 생성 (Claude Opus 4.5)
- backtranslate: 역번역 (Claude Sonnet 4.5)
- evaluate_accuracy: 정확성 평가 (Claude Sonnet 4.5)
- evaluate_compliance: 규정 준수 평가 (Claude Sonnet 4.5)
- evaluate_quality: 품질 평가 (Claude Opus 4.5)

사용 예:
    import asyncio
    from src.tools import translate, backtranslate, evaluate_accuracy

    async def main():
        # 번역
        result = await translate("안녕하세요", "ko", "en-rUS")

        # 역번역
        bt = await backtranslate(result.translation, "en-rUS", "ko")

        # 병렬 평가
        accuracy, compliance, quality = await asyncio.gather(
            evaluate_accuracy(source, result.translation, bt.backtranslation),
            evaluate_compliance(source, result.translation),
            evaluate_quality(source, result.translation)
        )
"""

# 결과 타입 (src/models에서 정의)
from src.models import TranslationResult, BacktranslationResult

# 번역 도구
from src.tools.translator_tool import translate

# 역번역 도구
from src.tools.backtranslator_tool import backtranslate

# 정확성 평가 도구
from src.tools.accuracy_evaluator_tool import evaluate_accuracy

# 규정 준수 평가 도구
from src.tools.compliance_evaluator_tool import evaluate_compliance

# 품질 평가 도구
from src.tools.quality_evaluator_tool import evaluate_quality

__all__ = [
    # 결과 타입
    "TranslationResult",
    "BacktranslationResult",
    # 번역
    "translate",
    # 역번역
    "backtranslate",
    # 정확성 평가
    "evaluate_accuracy",
    # 규정 준수 평가
    "evaluate_compliance",
    # 품질 평가
    "evaluate_quality",
]
