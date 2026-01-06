"""
역번역 도구 - Strands Agent 기반 역번역

번역문을 원본 언어로 다시 번역하여 의미 보존을 검증합니다.
정확성 평가 에이전트가 원문과 비교하는 데 사용됩니다.

모델: Claude Sonnet 4.5 (빠른 처리용)
"""

import json
import re
import time
import logging
from textwrap import dedent
from typing import Dict, Optional, Any

from src.models import BacktranslationResult
from src.utils.strands_utils import get_agent, run_agent_async
from src.prompts.template import load_prompt

logger = logging.getLogger(__name__)

# ANSI 색상 코드
MAGENTA = '\033[95m'
RESET = '\033[0m'


async def backtranslate(
    text: str,
    source_lang: str,
    target_lang: str,
    use_cache: bool = True,
    key: Optional[str] = None
) -> BacktranslationResult:
    """
    텍스트를 역번역.

    Args:
        text: 역번역할 텍스트 (번역된 텍스트)
        source_lang: 현재 텍스트의 언어 (번역 결과 언어, 예: "en-rUS")
        target_lang: 역번역 대상 언어 (원본 언어, 예: "ko")
        use_cache: 프롬프트 캐싱 사용 여부

    Returns:
        BacktranslationResult: 역번역 결과

    Example:
        # 영어 번역문을 한국어로 역번역
        result = await backtranslate(
            text="ABC Cloud syncs your data",
            source_lang="en-rUS",
            target_lang="ko"
        )
        # result.backtranslation = "ABC 클라우드는 당신의 데이터를 동기화합니다"

        # 병렬 실행 (여러 번역문 동시 역번역)
        results = await asyncio.gather(
            backtranslate(text1, "en-rUS", "ko"),
            backtranslate(text2, "ja", "ko"),
            backtranslate(text3, "de", "ko")
        )
    """
    start_time = time.time()

    # 시스템 프롬프트 로드
    system_prompt = _build_system_prompt(source_lang, target_lang)

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{MAGENTA}{'='*60}\n"
            f"[Backtranslator]{key_label} SYSTEM PROMPT\n"
            f"{'='*60}{RESET}\n"
            f"{system_prompt}\n"
            f"{MAGENTA}{'='*60}{RESET}"
        )

    # 에이전트 생성 (프롬프트 캐싱 포함)
    agent = get_agent(
        role="backtranslator",
        system_prompt=system_prompt,
        agent_name="backtranslator",
        prompt_cache=use_cache
    )

    # 사용자 메시지 구성
    user_message = dedent(f"""\
        <source_text>
        {text}
        </source_text>

        위 텍스트를 {target_lang}로 역번역하세요. 가능한 한 직역하여 원래 의미를 드러내세요.\
    """)

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{MAGENTA}{'='*60}\n"
            f"[Backtranslator]{key_label} USER PROMPT\n"
            f"{'='*60}{RESET}\n"
            f"{user_message}\n"
            f"{MAGENTA}{'='*60}{RESET}"
        )

    # 에이전트 비동기 실행
    try:
        result = await run_agent_async(agent, user_message)
        response_text = result["text"]
        usage = result["usage"]
    except Exception as e:
        logger.error(f"역번역 에이전트 실행 실패: {e}")
        raise

    # 응답 파싱
    parsed = _parse_backtranslation_response(response_text)

    latency_ms = int((time.time() - start_time) * 1000)

    return BacktranslationResult(
        backtranslation=parsed["backtranslation"],
        notes=parsed.get("notes"),
        token_usage=usage,
        latency_ms=latency_ms
    )


def _build_system_prompt(source_lang: str, target_lang: str) -> str:
    """시스템 프롬프트 구성"""

    return load_prompt(
        "backtranslator",
        source_lang=source_lang,
        target_lang=target_lang
    )


def _parse_backtranslation_response(response_text: str) -> Dict[str, Any]:
    """
    에이전트 응답 파싱.

    JSON 블록을 추출하고 역번역 결과를 반환합니다.
    """
    # JSON 블록 추출
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        json_str = json_match.group() if json_match else None

    if json_str:
        try:
            data = json.loads(json_str)
            return {
                "backtranslation": data.get("backtranslation", ""),
                "notes": data.get("notes")
            }
        except json.JSONDecodeError:
            pass

    # 파싱 실패 시 전체 응답을 역번역으로 사용
    logger.warning("JSON 파싱 실패, 원시 응답 사용")
    return {
        "backtranslation": response_text.strip(),
        "notes": None
    }
