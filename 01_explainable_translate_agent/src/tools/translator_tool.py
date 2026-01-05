"""
번역 도구 - Strands Agent 기반 번역

프롬프트 캐싱으로 시스템 프롬프트 비용 90% 절감.
모델: Claude Opus 4.5 (고품질 번역용)
"""

import json
import re
import time
import logging
from typing import Dict, Optional, Any

from src.models import TranslationResult
from src.utils.strands_utils import get_agent, run_agent_async
from src.prompts.template import load_prompt

logger = logging.getLogger(__name__)


async def translate(
    source_text: str,
    source_lang: str,
    target_lang: str,
    glossary: Optional[Dict[str, str]] = None,
    style_guide: Optional[Dict[str, str]] = None,
    feedback: Optional[str] = None,
    num_candidates: int = 1,
    use_cache: bool = True,
    key: Optional[str] = None
) -> TranslationResult:
    """
    소스 텍스트를 대상 언어로 번역.

    Args:
        source_text: 번역할 원문
        source_lang: 소스 언어 코드 (예: "ko")
        target_lang: 대상 언어 코드 (예: "en-rUS")
        glossary: 용어집 매핑 (예: {"ABC 클라우드": "ABC Cloud"})
        style_guide: 스타일 가이드 (예: {"tone": "formal"})
        feedback: 재생성용 이전 피드백 (Maker-Checker 루프)
        num_candidates: 생성할 번역 후보 수 (1 또는 2)
        use_cache: 프롬프트 캐싱 사용 여부

    Returns:
        TranslationResult: 번역 결과

    Example:
        # 단일 번역
        result = await translate("안녕하세요", "ko", "en-rUS")

        # 병렬 번역 (여러 언어)
        results = await asyncio.gather(
            translate(text, "ko", "en-rUS"),
            translate(text, "ko", "ja"),
            translate(text, "ko", "de")
        )
    """
    start_time = time.time()

    # 시스템 프롬프트 로드 및 렌더링
    system_prompt = _build_system_prompt(
        source_lang=source_lang,
        target_lang=target_lang,
        glossary=glossary,
        style_guide=style_guide,
        key=key
    )

    # 에이전트 생성 (프롬프트 캐싱 포함)
    agent = get_agent(
        role="translator",
        system_prompt=system_prompt,
        agent_name="translator",
        prompt_cache=use_cache
    )

    # 사용자 메시지 구성
    user_message = _build_user_message(
        source_text=source_text,
        feedback=feedback,
        num_candidates=num_candidates
    )

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{'='*60}\n"
            f"[Translator]{key_label} USER PROMPT\n"
            f"{'='*60}\n"
            f"{user_message}\n"
            f"{'='*60}"
        )

    # 에이전트 비동기 실행
    try:
        result = await run_agent_async(agent, user_message)
        response_text = result["text"]
        usage = result["usage"]
    except Exception as e:
        logger.error(f"번역 에이전트 실행 실패: {e}")
        raise

    # 응답 파싱
    parsed = _parse_translation_response(response_text)

    latency_ms = int((time.time() - start_time) * 1000)

    return TranslationResult(
        translation=parsed["translation"],
        candidates=parsed["candidates"],
        notes=parsed.get("notes"),
        token_usage=usage,
        latency_ms=latency_ms
    )


def _build_system_prompt(
    source_lang: str,
    target_lang: str,
    glossary: Optional[Dict[str, str]] = None,
    style_guide: Optional[Dict[str, str]] = None,
    key: Optional[str] = None
) -> str:
    """시스템 프롬프트 구성"""

    # 용어집 포맷
    glossary_text = ""
    if glossary:
        glossary_lines = [f"- {src} → {tgt}" for src, tgt in glossary.items()]
        glossary_text = "\n".join(glossary_lines)
    else:
        glossary_text = "(용어집 없음)"

    # 스타일 가이드 포맷
    style_text = ""
    if style_guide:
        style_lines = [f"- {k}: {v}" for k, v in style_guide.items()]
        style_text = "\n".join(style_lines)
    else:
        style_text = "(기본 스타일)"

    # 프롬프트 템플릿 로드 및 렌더링
    prompt = load_prompt(
        "translator",
        source_lang=source_lang,
        target_lang=target_lang,
        glossary=glossary_text,
        style_guide=style_text
    )

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{'='*60}\n"
            f"[Translator]{key_label} SYSTEM PROMPT\n"
            f"{'='*60}\n"
            f"{prompt}\n"
            f"{'='*60}"
        )

    return prompt


def _build_user_message(
    source_text: str,
    feedback: Optional[str] = None,
    num_candidates: int = 1
) -> str:
    """사용자 메시지 구성"""
    parts = []

    # 피드백이 있으면 추가 (Maker-Checker 루프)
    if feedback:
        parts.append(feedback)
        parts.append("")

    # 원문
    parts.append("<source_text>")
    parts.append(source_text)
    parts.append("</source_text>")

    # 후보 수 지시
    if num_candidates > 1:
        parts.append("")
        parts.append(f"<instruction>")
        parts.append(f"{num_candidates}개의 번역 후보를 생성하세요.")
        parts.append(f"candidates 배열에 모든 후보를 포함하세요.")
        parts.append(f"</instruction>")

    return "\n".join(parts)


def _parse_translation_response(response_text: str) -> Dict[str, Any]:
    """에이전트 응답 파싱 - JSON 블록 추출"""
    # JSON 블록 추출
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        # JSON 블록이 없으면 전체에서 JSON 찾기
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        json_str = json_match.group() if json_match else None

    if json_str:
        try:
            data = json.loads(json_str)

            # 단일 번역
            translation = data.get("translation", "")

            # 후보 추출
            candidates = data.get("candidates", [translation])
            if not candidates:
                candidates = [translation]

            # 첫 번째 후보를 메인 번역으로
            if not translation and candidates:
                translation = candidates[0]

            return {
                "translation": translation,
                "candidates": candidates,
                "notes": data.get("notes")
            }
        except json.JSONDecodeError:
            pass

    # 파싱 실패 시 전체 응답을 번역으로 사용
    logger.warning("JSON 파싱 실패, 원시 응답 사용")
    return {
        "translation": response_text.strip(),
        "candidates": [response_text.strip()],
        "notes": None
    }
