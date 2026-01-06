"""
정확성 평가 도구 - Strands Agent 기반 정확성 평가

번역의 의미 충실도, 용어집 적용, 포맷 무결성을 평가합니다.
역번역을 원문과 비교하여 의미 손실/추가를 감지합니다.

모델: Claude Sonnet 4.5
"""

import json
import re
import time
import logging
from textwrap import dedent
from typing import Dict, Optional, Any

from src.models.agent_result import AgentResult, Correction
from src.utils.strands_utils import get_agent, run_agent_async
from src.prompts.template import load_prompt

logger = logging.getLogger(__name__)

# ANSI 색상 코드
CYAN = '\033[96m'
RESET = '\033[0m'


async def evaluate_accuracy(
    source_text: str,
    translation: str,
    backtranslation: str,
    source_lang: str = "ko",
    target_lang: str = "en-rUS",
    glossary: Optional[Dict[str, str]] = None,
    use_cache: bool = True,
    key: Optional[str] = None
) -> AgentResult:
    """
    번역의 정확성 평가.

    Args:
        source_text: 원문
        translation: 번역문
        backtranslation: 역번역문
        source_lang: 원본 언어 코드
        target_lang: 대상 언어 코드
        glossary: 용어집 매핑
        use_cache: 프롬프트 캐싱 사용 여부

    Returns:
        AgentResult: 평가 결과 (점수, 판정, 이슈, 수정 제안)

    Example:
        result = await evaluate_accuracy(
            source_text="ABC 클라우드는 데이터를 동기화합니다.",
            translation="ABC Cloud syncs your data.",
            backtranslation="ABC 클라우드는 당신의 데이터를 동기화합니다.",
            glossary={"ABC 클라우드": "ABC Cloud"}
        )
        print(result.score)  # 5
        print(result.verdict)  # "pass"

        # 병렬 평가 (다른 평가 에이전트와 함께)
        accuracy, compliance, quality = await asyncio.gather(
            evaluate_accuracy(source, translation, backtranslation),
            evaluate_compliance(source, translation),
            evaluate_quality(source, translation)
        )
    """
    start_time = time.time()

    # 시스템 프롬프트 로드
    system_prompt = _build_system_prompt(source_lang, target_lang)

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{CYAN}{'='*60}\n"
            f"[Accuracy]{key_label} SYSTEM PROMPT\n"
            f"{'='*60}{RESET}\n"
            f"{system_prompt}\n"
            f"{CYAN}{'='*60}{RESET}"
        )

    # 에이전트 생성
    agent = get_agent(
        role="accuracy_evaluator",
        system_prompt=system_prompt,
        agent_name="accuracy_evaluator",
        prompt_cache=use_cache
    )

    # 사용자 메시지 구성
    user_message = _build_user_message(
        source_text=source_text,
        translation=translation,
        backtranslation=backtranslation,
        glossary=glossary
    )

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{CYAN}{'='*60}\n"
            f"[Accuracy]{key_label} USER PROMPT\n"
            f"{'='*60}{RESET}\n"
            f"{user_message}\n"
            f"{CYAN}{'='*60}{RESET}"
        )

    # 에이전트 비동기 실행
    try:
        result = await run_agent_async(agent, user_message)
        response_text = result["text"]
        usage = result["usage"]
    except Exception as e:
        logger.error(f"정확성 평가 에이전트 실행 실패: {e}")
        raise

    # 응답 파싱
    parsed = _parse_evaluation_response(response_text)

    latency_ms = int((time.time() - start_time) * 1000)

    # AgentResult 생성
    return AgentResult(
        agent_name="accuracy",
        reasoning_chain=parsed.get("reasoning_chain", []),
        score=parsed.get("score", 0),
        verdict=parsed.get("verdict", "fail"),
        issues=parsed.get("issues", []),
        corrections=parsed.get("corrections", []),
        token_usage=usage,
        latency_ms=latency_ms
    )


def _build_system_prompt(source_lang: str, target_lang: str) -> str:
    """시스템 프롬프트 구성"""

    return load_prompt(
        "accuracy_evaluator",
        source_lang=source_lang,
        target_lang=target_lang
    )


def _build_user_message(
    source_text: str,
    translation: str,
    backtranslation: str,
    glossary: Optional[Dict[str, str]] = None
) -> str:
    """사용자 메시지 구성"""
    if glossary:
        glossary_lines = [f"- {src} → {tgt}" for src, tgt in glossary.items()]
        glossary_text = "\n".join(glossary_lines)
    else:
        glossary_text = "(용어집 없음)"

    return dedent(f"""\
        다음 번역을 정확성 관점에서 평가하세요.

        <source_text>
        {source_text}
        </source_text>

        <translation>
        {translation}
        </translation>

        <backtranslation>
        {backtranslation}
        </backtranslation>

        <glossary>
        {glossary_text}
        </glossary>

        위 내용을 바탕으로 정확성을 평가하고 결과를 JSON 형식으로 반환하세요.\
    """)


def _parse_evaluation_response(response_text: str) -> Dict[str, Any]:
    """에이전트 응답 파싱"""

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

            # Correction 객체 변환
            corrections = []
            for c in data.get("corrections", []):
                corrections.append(Correction(
                    original=c.get("original", ""),
                    suggested=c.get("suggested", ""),
                    reason=c.get("reason", "")
                ))

            return {
                "reasoning_chain": data.get("reasoning_chain", []),
                "score": data.get("score", 0),
                "verdict": data.get("verdict", "fail"),
                "issues": data.get("issues", []),
                "corrections": corrections
            }
        except json.JSONDecodeError:
            pass

    # 파싱 실패
    logger.warning("JSON 파싱 실패, 기본값 사용")
    return {
        "reasoning_chain": [response_text[:500]],
        "score": 0,
        "verdict": "fail",
        "issues": ["평가 결과 파싱 실패"],
        "corrections": []
    }
