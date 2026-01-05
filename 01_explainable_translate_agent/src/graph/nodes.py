"""
워크플로우 노드 - 번역 파이프라인의 각 단계 구현

각 노드는 하나의 워크플로우 단계를 담당:
- translate_node: 번역 생성
- backtranslate_node: 역번역 (검증용)
- evaluate_node: 3개 에이전트 병렬 평가
- decide_node: Release Guard 판정
- regenerate_node: 재생성 준비 (피드백 수집)
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from src.models.translation_unit import TranslationUnit
from src.models.gate_decision import GateDecision, Verdict
from src.models.workflow_state import WorkflowState
from src.tools import (
    translate,
    backtranslate,
    evaluate_accuracy,
    evaluate_compliance,
    evaluate_quality,
    TranslationResult,
    BacktranslationResult
)
from sops.evaluation_gate import EvaluationGateSOP, EvaluationGateConfig
from sops.regeneration import RegenerationSOP
from src.utils.config import get_glossary, get_style_guide, get_risk_profile

logger = logging.getLogger(__name__)


async def translate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    번역 생성 노드.

    원문을 대상 언어로 번역합니다.
    재생성 시에는 이전 피드백을 반영합니다.

    Args:
        state: 워크플로우 상태
            - unit: TranslationUnit (필수)
            - feedback: 재생성용 피드백 (선택)
            - num_candidates: 생성할 후보 수 (기본: 1)

    Returns:
        업데이트된 상태:
            - translation_result: TranslationResult
            - workflow_state: TRANSLATING
    """
    unit: TranslationUnit = state["unit"]
    feedback: Optional[str] = state.get("feedback")
    num_candidates: int = state.get("num_candidates", 1)

    # 용어집/스타일 가이드 로드 (data/{glossaries,style_guides}/{product}/{lang}.yaml)
    # TODO: inline glossary/style_guide 지원 제거 예정
    glossary = get_glossary(unit.product, unit.target_lang)
    style_guide = get_style_guide(unit.product, unit.target_lang)
    logger.info(f"번역 시작: {unit.key} ({unit.source_lang} → {unit.target_lang}), 용어집: {len(glossary)}개, 스타일: {len(style_guide)}개")

    try:
        result: TranslationResult = await translate(
            source_text=unit.source_text,
            source_lang=unit.source_lang,
            target_lang=unit.target_lang,
            glossary=glossary,
            style_guide=style_guide,
            feedback=feedback,
            num_candidates=num_candidates,
            key=unit.key
        )

        state["translation_result"] = result
        state["workflow_state"] = WorkflowState.TRANSLATING

        logger.info(f"[{unit.key}] 번역 완료: {len(result.candidates)}개 후보 ({result.latency_ms}ms)")

    except Exception as e:
        logger.error(f"[{unit.key}] 번역 실패: {e}")
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)
        raise

    return state


async def backtranslate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    역번역 노드.

    번역 결과를 원본 언어로 다시 번역하여
    정확성 평가에서 의미 보존을 검증하는 데 사용합니다.

    Args:
        state: 워크플로우 상태
            - translation_result: TranslationResult (필수)
            - unit: TranslationUnit (필수)

    Returns:
        업데이트된 상태:
            - backtranslation_result: BacktranslationResult
            - workflow_state: BACKTRANSLATING
    """
    translation_result: TranslationResult = state["translation_result"]
    unit: TranslationUnit = state["unit"]

    # 첫 번째 후보 (또는 선택된 번역)를 역번역
    text_to_backtranslate = translation_result.translation

    logger.info(f"[{unit.key}] 역번역 시작")

    try:
        result: BacktranslationResult = await backtranslate(
            text=text_to_backtranslate,
            source_lang=unit.target_lang,  # 번역된 언어
            target_lang=unit.source_lang   # 원본 언어로 역번역
        )

        state["backtranslation_result"] = result
        state["workflow_state"] = WorkflowState.BACKTRANSLATING

        logger.info(f"[{unit.key}] 역번역 완료 ({result.latency_ms}ms)")

    except Exception as e:
        logger.error(f"[{unit.key}] 역번역 실패: {e}")
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)
        raise

    return state


async def evaluate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    평가 노드 - 3개 에이전트 병렬 실행.

    정확성, 규정 준수, 품질 평가 에이전트를 동시에 실행합니다.

    Args:
        state: 워크플로우 상태
            - unit: TranslationUnit (필수)
            - translation_result: TranslationResult (필수)
            - backtranslation_result: BacktranslationResult (필수)

    Returns:
        업데이트된 상태:
            - agent_results: List[AgentResult]
            - eval_start_time: datetime
            - workflow_state: EVALUATING
    """
    unit: TranslationUnit = state["unit"]
    translation_result: TranslationResult = state["translation_result"]
    backtranslation_result: BacktranslationResult = state["backtranslation_result"]

    translation = translation_result.translation
    backtranslation = backtranslation_result.backtranslation
    candidates = translation_result.candidates

    # 리스크 프로파일 로드 (data/risk_profiles/{country}.yaml)
    risk_profile = get_risk_profile(unit.risk_profile)

    eval_start_time = datetime.now()

    logger.info(f"[{unit.key}] 평가 시작 (3개 에이전트 병렬), 리스크 프로파일: {unit.risk_profile}")

    try:
        # 3개 에이전트 병렬 실행
        results = await asyncio.gather(
            evaluate_accuracy(
                source_text=unit.source_text,
                translation=translation,
                backtranslation=backtranslation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                glossary=unit.glossary
            ),
            evaluate_compliance(
                source_text=unit.source_text,
                translation=translation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                risk_profile=risk_profile,
                content_context="FAQ"
            ),
            evaluate_quality(
                source_text=unit.source_text,
                translation=translation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                candidates=candidates if len(candidates) > 1 else None,
                content_type="FAQ",
                glossary=unit.glossary
            ),
            return_exceptions=True
        )

        # 예외 처리
        agent_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_names = ["accuracy", "compliance", "quality"]
                logger.error(f"[{unit.key}] {agent_names[i]} 평가 실패: {result}")
                raise result
            agent_results.append(result)

        state["agent_results"] = agent_results
        state["eval_start_time"] = eval_start_time
        state["workflow_state"] = WorkflowState.EVALUATING

        # 로깅
        scores = {r.agent_name: r.score for r in agent_results}
        total_latency = sum(r.latency_ms for r in agent_results)
        logger.info(f"[{unit.key}] 평가 완료: {scores} ({total_latency}ms)")

    except Exception as e:
        logger.error(f"[{unit.key}] 평가 실패: {e}")
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)
        raise

    return state


async def decide_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    판정 노드 - Release Guard.

    3개 에이전트의 평가 결과를 기반으로 최종 판정을 결정합니다.
    - PASS: 모든 에이전트 점수 >= 4
    - BLOCK: 어떤 에이전트라도 점수 <= 2
    - REGENERATE: 경계 점수 (3점), 재시도 가능
    - ESCALATE: 에이전트 불일치 또는 재시도 소진

    Args:
        state: 워크플로우 상태
            - agent_results: List[AgentResult] (필수)
            - attempt_count: 현재 시도 횟수 (기본: 1)
            - eval_start_time: 평가 시작 시간 (선택)

    Returns:
        업데이트된 상태:
            - gate_decision: GateDecision
            - workflow_state: DECIDING
    """
    unit: TranslationUnit = state["unit"]
    agent_results = state["agent_results"]
    attempt_count = state.get("attempt_count", 1)
    max_regenerations = state.get("max_regenerations", 1)
    eval_start_time = state.get("eval_start_time")

    logger.info(f"[{unit.key}] 판정 시작 (시도 {attempt_count}/{max_regenerations+1})")

    # SOP 실행 (워크플로우 설정의 max_regenerations 사용)
    gate_config = EvaluationGateConfig(max_regenerations=max_regenerations)
    gate_sop = EvaluationGateSOP(config=gate_config)
    decision = gate_sop.decide(
        agent_results=agent_results,
        attempt_count=attempt_count,
        start_time=eval_start_time
    )

    state["gate_decision"] = decision
    state["workflow_state"] = WorkflowState.DECIDING

    # 시도 히스토리 저장 (디버깅용 상세 정보 포함)
    if "attempt_history" not in state:
        state["attempt_history"] = []

    # 문제 에이전트의 이슈와 수정 제안 수집
    issues_by_agent = {}
    corrections_by_agent = {}
    for ar in agent_results:
        if ar.score < 5:  # 5점 미만인 에이전트
            if ar.issues:
                issues_by_agent[ar.agent_name] = ar.issues
            if ar.corrections:
                corrections_by_agent[ar.agent_name] = [
                    {"original": c.original, "suggested": c.suggested, "reason": c.reason}
                    for c in ar.corrections
                ]

    state["attempt_history"].append({
        "attempt": attempt_count,
        "verdict": decision.verdict.value,
        "scores": decision.scores.copy(),
        "message": decision.message,
        "review_agents": decision.review_agents.copy() if decision.review_agents else [],
        "issues": issues_by_agent,
        "corrections": corrections_by_agent,
    })

    logger.info(f"[{unit.key}] 판정: {decision.verdict.value}")

    return state


async def regenerate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    재생성 준비 노드.

    평가 결과에서 피드백을 수집하고 번역기에 전달할 형태로 포맷합니다.
    다음 번역 시도에서 이전 문제를 피할 수 있도록 안내합니다.

    Args:
        state: 워크플로우 상태
            - agent_results: List[AgentResult] (필수)
            - translation_result: TranslationResult (필수)
            - attempt_count: 현재 시도 횟수 (필수)

    Returns:
        업데이트된 상태:
            - feedback: 포맷된 피드백 문자열
            - attempt_count: 증가된 시도 횟수
            - workflow_state: REGENERATING
    """
    unit: TranslationUnit = state["unit"]
    agent_results = state["agent_results"]
    translation_result: TranslationResult = state["translation_result"]
    attempt_count = state.get("attempt_count", 1)

    logger.info(f"[{unit.key}] 재생성 준비 (시도 {attempt_count} → {attempt_count + 1})")

    # 피드백 수집
    regen_sop = RegenerationSOP()
    feedback = regen_sop.collect_feedback(
        agent_results=agent_results,
        previous_translation=translation_result.translation
    )

    # 피드백 포맷
    feedback_text = regen_sop.format_feedback_for_prompt(
        feedback=feedback,
        include_reasoning=True,
        language="ko"
    )

    state["feedback"] = feedback_text
    state["attempt_count"] = attempt_count + 1
    state["workflow_state"] = WorkflowState.REGENERATING

    # 피드백 통계 로깅
    logger.info(
        f"[{unit.key}] 피드백: "
        f"{len(feedback.previous_issues)}개 이슈, "
        f"{len(feedback.corrections)}개 수정"
    )

    return state


async def finalize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    최종 상태 설정 노드.

    판정 결과에 따라 최종 워크플로우 상태를 설정합니다.

    Args:
        state: 워크플로우 상태
            - gate_decision: GateDecision (필수)

    Returns:
        업데이트된 상태:
            - workflow_state: 최종 상태 (PUBLISHED, REJECTED, PENDING_REVIEW)
            - final_translation: 최종 번역 (PASS인 경우)
    """
    unit: TranslationUnit = state["unit"]
    decision: GateDecision = state["gate_decision"]
    translation_result: TranslationResult = state["translation_result"]

    if decision.verdict == Verdict.PASS:
        state["workflow_state"] = WorkflowState.PUBLISHED
        state["final_translation"] = translation_result.translation
        logger.info(f"[{unit.key}] 발행 완료")

    elif decision.verdict == Verdict.BLOCK:
        state["workflow_state"] = WorkflowState.REJECTED
        logger.warning(f"[{unit.key}] 거부됨")

    elif decision.verdict == Verdict.ESCALATE:
        state["workflow_state"] = WorkflowState.PENDING_REVIEW
        logger.info(f"[{unit.key}] PM 검수 대기")

    return state
