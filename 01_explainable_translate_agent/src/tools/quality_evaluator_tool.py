"""
품질 평가 도구 - Strands Agent 기반 품질 평가

번역의 유창성, 톤, 문화적 적합성을 평가합니다.
원어민 관점에서 텍스트가 자연스럽게 읽히는지 평가합니다.
여러 후보 비교 시 최적의 번역을 선택합니다.

모델: Claude Opus 4.5 (원어민 수준 평가용)
"""

import json
import re
import time
import logging
from textwrap import dedent
from typing import Dict, List, Optional, Any

from src.models.agent_result import AgentResult, Correction
from src.utils.strands_utils import get_agent, run_agent_async
from src.prompts.template import load_prompt

logger = logging.getLogger(__name__)


async def evaluate_quality(
    source_text: str,
    translation: str,
    source_lang: str = "ko",
    target_lang: str = "en-rUS",
    candidates: Optional[List[str]] = None,
    content_type: str = "FAQ",
    glossary: Optional[Dict[str, str]] = None,
    locale_guidelines: Optional[str] = None,
    use_cache: bool = True
) -> AgentResult:
    """
    번역의 품질 평가.

    Args:
        source_text: 원문
        translation: 번역문 (또는 첫 번째 후보)
        source_lang: 원본 언어 코드
        target_lang: 대상 언어 코드
        candidates: 비교할 번역 후보 목록 (선택)
        content_type: 콘텐츠 유형 (FAQ, Legal, UI 등)
        glossary: 용어집 (수정 제안 시 반드시 준수)
        locale_guidelines: 로케일별 가이드라인
        use_cache: 프롬프트 캐싱 사용 여부

    Returns:
        AgentResult: 평가 결과 (점수, 판정, 이슈, 선택된 후보)

    Example:
        # 단일 번역 평가
        result = await evaluate_quality(
            source_text="데이터를 백업하세요",
            translation="Please back up your data",
            content_type="FAQ"
        )

        # 여러 후보 비교
        result = await evaluate_quality(
            source_text="데이터를 백업하세요",
            translation="Please back up your data",
            candidates=[
                "Please back up your data",
                "Backup your data"
            ]
        )
        print(result.score)  # 5

        # 병렬 평가 (다른 평가 에이전트와 함께)
        accuracy, compliance, quality = await asyncio.gather(
            evaluate_accuracy(source, translation, backtranslation),
            evaluate_compliance(source, translation),
            evaluate_quality(source, translation)
        )
    """
    start_time = time.time()

    # 시스템 프롬프트 로드
    system_prompt = _build_system_prompt(
        source_lang=source_lang,
        target_lang=target_lang,
        locale_guidelines=locale_guidelines
    )

    # 에이전트 생성
    agent = get_agent(
        role="quality_evaluator",
        system_prompt=system_prompt,
        agent_name="quality_evaluator",
        prompt_cache=use_cache
    )

    # 사용자 메시지 구성
    user_message = _build_user_message(
        source_text=source_text,
        translation=translation,
        candidates=candidates,
        content_type=content_type,
        glossary=glossary
    )

    # 에이전트 비동기 실행
    try:
        result = await run_agent_async(agent, user_message)
        response_text = result["text"]
        usage = result["usage"]
    except Exception as e:
        logger.error(f"품질 평가 에이전트 실행 실패: {e}")
        raise

    # 응답 파싱
    parsed = _parse_evaluation_response(response_text)

    latency_ms = int((time.time() - start_time) * 1000)

    # AgentResult 생성
    return AgentResult(
        agent_name="quality",
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
    locale_guidelines: Optional[str] = None
) -> str:
    """시스템 프롬프트 구성"""

    guidelines = locale_guidelines or ""

    return load_prompt(
        "quality_evaluator",
        source_lang=source_lang,
        target_lang=target_lang,
        locale_guidelines=guidelines
    )


def _build_user_message(
    source_text: str,
    translation: str,
    candidates: Optional[List[str]] = None,
    content_type: str = "FAQ",
    glossary: Optional[Dict[str, str]] = None
) -> str:
    """사용자 메시지 구성"""
    # 후보 텍스트 구성
    candidates_section = ""
    if candidates and len(candidates) > 1:
        candidate_lines = [f"후보 {i}: {c}" for i, c in enumerate(candidates)]
        candidates_text = "\n".join(candidate_lines)
        candidates_section = dedent(f"""\

            <candidates>
            {candidates_text}
            </candidates>
        """)

    # 용어집 섹션 구성
    glossary_section = ""
    if glossary:
        glossary_lines = [f"  {k} → {v}" for k, v in glossary.items()]
        glossary_text = "\n".join(glossary_lines)
        glossary_section = dedent(f"""\

            <glossary>
            {glossary_text}
            </glossary>
        """)

    return dedent(f"""\
        다음 번역을 품질 관점에서 평가하세요.

        <source_text>
        {source_text}
        </source_text>

        <translation>
        {translation}
        </translation>{candidates_section}{glossary_section}
        <content_type>
        {content_type}
        </content_type>

        위 내용을 바탕으로 품질을 평가하고 결과를 JSON 형식으로 반환하세요.\
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

            # 후보 비교 정보 추가
            issues = data.get("issues", [])
            if "comparison_notes" in data:
                issues.append(f"[비교] {data['comparison_notes']}")

            result = {
                "reasoning_chain": data.get("reasoning_chain", []),
                "score": data.get("score", 0),
                "verdict": data.get("verdict", "fail"),
                "issues": issues,
                "corrections": corrections
            }

            # 선택된 후보 정보 추가
            if "selected_candidate" in data:
                result["selected_candidate"] = data["selected_candidate"]
            if "candidate_scores" in data:
                result["candidate_scores"] = data["candidate_scores"]

            return result
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
