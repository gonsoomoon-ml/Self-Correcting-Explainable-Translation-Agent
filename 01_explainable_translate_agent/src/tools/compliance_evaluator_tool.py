"""
규정 준수 평가 도구 - Strands Agent 기반 규제 준수 평가

번역의 법적, 규제적, 콘텐츠 안전 준수를 평가합니다.
국가별 리스크 프로파일을 기반으로 금칙어, 면책문구, 규제 위반을 검사합니다.

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
YELLOW = '\033[93m'
RESET = '\033[0m'


async def evaluate_compliance(
    source_text: str,
    translation: str,
    source_lang: str = "ko",
    target_lang: str = "en-rUS",
    risk_profile: Optional[Dict[str, Any]] = None,
    content_context: str = "FAQ",
    use_cache: bool = True,
    key: Optional[str] = None
) -> AgentResult:
    """
    번역의 규정 준수 평가.

    Args:
        source_text: 원문
        translation: 번역문
        source_lang: 원본 언어 코드
        target_lang: 대상 언어 코드
        risk_profile: 국가별 리스크 프로파일 (금칙어, 면책문구 등)
        content_context: 콘텐츠 유형 (FAQ, Legal, Marketing 등)
        use_cache: 프롬프트 캐싱 사용 여부

    Returns:
        AgentResult: 평가 결과 (점수, 판정, 이슈, 리스크 플래그)

    Example:
        result = await evaluate_compliance(
            source_text="100% 환불 보장",
            translation="100% refund guaranteed",
            risk_profile={
                "prohibited_terms": [{"term": "guaranteed", "severity": "high"}]
            }
        )
        print(result.score)  # 2
        print(result.issues)  # ["금칙어 사용: guaranteed"]

        # 병렬 평가 (다른 평가 에이전트와 함께)
        accuracy, compliance, quality = await asyncio.gather(
            evaluate_accuracy(source, translation, backtranslation),
            evaluate_compliance(source, translation, risk_profile=profile),
            evaluate_quality(source, translation)
        )
    """
    start_time = time.time()

    # 시스템 프롬프트 로드 (risk_profile 포함 - 캐싱 최적화)
    system_prompt = _build_system_prompt(
        source_lang=source_lang,
        target_lang=target_lang,
        risk_profile=risk_profile,
        content_context=content_context
    )

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{YELLOW}{'='*60}\n"
            f"[Compliance]{key_label} SYSTEM PROMPT (with risk_profile - cached)\n"
            f"{'='*60}{RESET}\n"
            f"{system_prompt}\n"
            f"{YELLOW}{'='*60}{RESET}"
        )

    # 에이전트 생성
    agent = get_agent(
        role="compliance_evaluator",
        system_prompt=system_prompt,
        agent_name="compliance_evaluator",
        prompt_cache=use_cache
    )

    # 사용자 메시지 구성 (source_text, translation만 - 매번 변경)
    user_message = _build_user_message(
        source_text=source_text,
        translation=translation
    )

    if logger.isEnabledFor(logging.DEBUG):
        key_label = f" ({key})" if key else ""
        logger.debug(
            f"\n{YELLOW}{'='*60}\n"
            f"[Compliance]{key_label} USER PROMPT\n"
            f"{'='*60}{RESET}\n"
            f"{user_message}\n"
            f"{YELLOW}{'='*60}{RESET}"
        )

    # 에이전트 비동기 실행
    try:
        result = await run_agent_async(agent, user_message)
        response_text = result["text"]
        usage = result["usage"]
    except Exception as e:
        logger.error(f"규정 준수 평가 에이전트 실행 실패: {e}")
        raise

    # 응답 파싱
    parsed = _parse_evaluation_response(response_text)

    latency_ms = int((time.time() - start_time) * 1000)

    # AgentResult 생성
    return AgentResult(
        agent_name="compliance",
        reasoning_chain=parsed.get("reasoning_chain", []),
        score=parsed.get("score", 0),
        verdict=parsed.get("verdict", "fail"),
        issues=parsed.get("issues", []),
        corrections=parsed.get("corrections", []),
        token_usage=usage,
        latency_ms=latency_ms
    )


def _build_system_prompt(
    source_lang: str,
    target_lang: str,
    risk_profile: Optional[Dict[str, Any]] = None,
    content_context: str = "FAQ"
) -> str:
    """
    시스템 프롬프트 구성 (risk_profile 포함).

    risk_profile을 시스템 프롬프트에 포함하여 캐싱 최적화:
    - 같은 국가의 번역을 여러 개 처리할 때 시스템 프롬프트가 캐시됨
    - 금칙어/면책문구 목록이 매번 재전송되지 않음
    """
    base_prompt = load_prompt(
        "compliance_evaluator",
        source_lang=source_lang,
        target_lang=target_lang
    )

    # risk_profile을 시스템 프롬프트에 추가
    if risk_profile:
        risk_text = json.dumps(risk_profile, ensure_ascii=False, indent=2)
    else:
        risk_text = "(기본 리스크 프로파일 - 금칙어 없음)"

    risk_section = dedent(f"""
## Risk Profile
<risk_profile>
{risk_text}
</risk_profile>

## Content Context
<content_context>
{content_context}
</content_context>
""")

    return base_prompt + "\n" + risk_section


def _build_user_message(
    source_text: str,
    translation: str
) -> str:
    """
    사용자 메시지 구성 (source_text, translation만).

    risk_profile은 시스템 프롬프트로 이동하여 캐싱 최적화.
    사용자 메시지는 매번 변경되는 번역 내용만 포함.
    """
    return dedent(f"""\
        다음 번역을 규정 준수 관점에서 평가하세요.

        <source_text>
        {source_text}
        </source_text>

        <translation>
        {translation}
        </translation>

        위 내용을 바탕으로 규정 준수를 평가하고 결과를 JSON 형식으로 반환하세요.\
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

            # risk_flags를 issues에 추가
            issues = data.get("issues", [])
            for flag in data.get("risk_flags", []):
                flag_desc = f"[{flag.get('severity', 'unknown').upper()}] {flag.get('type')}: {flag.get('term')}"
                if flag_desc not in issues:
                    issues.append(flag_desc)

            return {
                "reasoning_chain": data.get("reasoning_chain", []),
                "score": data.get("score", 0),
                "verdict": data.get("verdict", "fail"),
                "issues": issues,
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
