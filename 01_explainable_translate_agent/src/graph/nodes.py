"""
워크플로우 노드 v2 - GraphBuilder 호환 버전

기존 nodes.py의 기능을 유지하면서 Strands GraphBuilder와 호환되도록 수정.
글로벌 상태 패턴을 사용하여 노드 간 데이터를 공유합니다.

주요 변경사항:
- 글로벌 상태 관리자 사용 (get_workflow_state)
- FunctionNode 래퍼와 호환되는 반환값

사용법:
    # GraphBuilder에서
    from src.graph.nodes import translate_node, evaluate_node
    from src.utils import FunctionNode

    builder.add_node(FunctionNode(translate_node, "translate"), "translate")
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
from src.utils.workflow_state import get_workflow_state, is_workflow_failed

logger = logging.getLogger(__name__)


async def translate_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    번역 생성 노드 (GraphBuilder 호환).

    글로벌 상태에서 unit과 feedback을 읽고 번역 결과를 저장합니다.

    Returns:
        {"text": "번역 완료", "success": True/False}
    """
    try:
        state = get_workflow_state()
        unit: TranslationUnit = state["unit"]
        feedback: Optional[str] = state.get("feedback")
        num_candidates: int = state.get("num_candidates", 1)

        # 용어집/스타일 가이드 로드
        glossary = get_glossary(unit.product, unit.target_lang)
        style_guide = get_style_guide(unit.product, unit.target_lang)

        logger.info(
            f"[{unit.key}] 번역 시작 ({unit.source_lang} → {unit.target_lang}), "
            f"용어집: {len(glossary)}개, 스타일: {len(style_guide)}개"
        )

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

        # 글로벌 상태 업데이트
        state["translation_result"] = result
        state["workflow_state"] = WorkflowState.TRANSLATING

        logger.info(f"[{unit.key}] 번역 완료: {len(result.candidates)}개 후보 ({result.latency_ms}ms)")

        return {"text": f"번역 완료: {unit.key}", "success": True}

    except Exception as e:
        logger.error(f"번역 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)
        return {"text": f"번역 실패: {e}", "success": False}


async def backtranslate_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    역번역 노드 (GraphBuilder 호환).

    번역 결과를 원본 언어로 다시 번역하여 정확성 검증에 사용합니다.
    """
    try:
        state = get_workflow_state()
        translation_result: TranslationResult = state["translation_result"]
        unit: TranslationUnit = state["unit"]

        text_to_backtranslate = translation_result.translation

        logger.info(f"[{unit.key}] 역번역 시작")

        result: BacktranslationResult = await backtranslate(
            text=text_to_backtranslate,
            source_lang=unit.target_lang,
            target_lang=unit.source_lang,
            key=unit.key
        )

        state["backtranslation_result"] = result
        state["workflow_state"] = WorkflowState.BACKTRANSLATING

        logger.info(f"[{unit.key}] 역번역 완료 ({result.latency_ms}ms)")

        return {"text": f"역번역 완료: {unit.key}", "success": True}

    except Exception as e:
        logger.error(f"역번역 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)
        return {"text": f"역번역 실패: {e}", "success": False}


async def evaluate_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    평가 노드 - 3개 에이전트 병렬 실행 (GraphBuilder 호환).

    정확성, 규정 준수, 품질 평가 에이전트를 동시에 실행합니다.
    """
    try:
        state = get_workflow_state()
        unit: TranslationUnit = state["unit"]
        translation_result: TranslationResult = state["translation_result"]
        backtranslation_result: BacktranslationResult = state["backtranslation_result"]

        translation = translation_result.translation
        backtranslation = backtranslation_result.backtranslation
        candidates = translation_result.candidates

        risk_profile = get_risk_profile(unit.risk_profile)
        eval_start_time = datetime.now()

        logger.info(f"[{unit.key}] 평가 시작 (3개 에이전트 병렬), 리스크 프로파일: {unit.risk_profile}")

        # 3개 에이전트 병렬 실행
        results = await asyncio.gather(
            evaluate_accuracy(
                source_text=unit.source_text,
                translation=translation,
                backtranslation=backtranslation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                glossary=unit.glossary,
                key=unit.key
            ),
            evaluate_compliance(
                source_text=unit.source_text,
                translation=translation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                risk_profile=risk_profile,
                content_context="FAQ",
                key=unit.key
            ),
            evaluate_quality(
                source_text=unit.source_text,
                translation=translation,
                source_lang=unit.source_lang,
                target_lang=unit.target_lang,
                candidates=candidates if len(candidates) > 1 else None,
                content_type="FAQ",
                glossary=unit.glossary,
                key=unit.key
            ),
            return_exceptions=True
        )

        # 예외 처리
        agent_results = []
        agent_names = ["accuracy", "compliance", "quality"]
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{unit.key}] {agent_names[i]} 평가 실패: {result}")
                raise result
            agent_results.append(result)

        state["agent_results"] = agent_results
        state["eval_start_time"] = eval_start_time
        state["workflow_state"] = WorkflowState.EVALUATING

        scores = {r.agent_name: r.score for r in agent_results}
        total_latency = sum(r.latency_ms for r in agent_results)
        logger.info(f"[{unit.key}] 평가 완료: {scores} ({total_latency}ms)")

        return {"text": f"평가 완료: {scores}", "success": True}

    except Exception as e:
        logger.error(f"평가 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)

        return {"text": f"평가 실패: {e}", "success": False}


async def decide_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    판정 노드 - Release Guard (GraphBuilder 호환).

    3개 에이전트의 평가 결과를 기반으로 최종 판정을 결정합니다.
    """
    try:
        state = get_workflow_state()
        unit: TranslationUnit = state["unit"]
        agent_results = state["agent_results"]
        attempt_count = state.get("attempt_count", 1)
        max_regenerations = state.get("max_regenerations", 1)
        eval_start_time = state.get("eval_start_time")

        logger.info(f"[{unit.key}] 판정 시작 (시도 {attempt_count}/{max_regenerations+1})")

        # SOP 실행
        gate_config = EvaluationGateConfig(max_regenerations=max_regenerations)
        gate_sop = EvaluationGateSOP(config=gate_config)
        decision = gate_sop.decide(
            agent_results=agent_results,
            attempt_count=attempt_count,
            start_time=eval_start_time
        )

        state["gate_decision"] = decision
        state["workflow_state"] = WorkflowState.DECIDING

        # 시도 히스토리 저장
        if "attempt_history" not in state:
            state["attempt_history"] = []

        issues_by_agent = {}
        corrections_by_agent = {}
        for ar in agent_results:
            if ar.score < 5:
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

        return {"text": f"판정: {decision.verdict.value}", "success": True}

    except Exception as e:
        logger.error(f"판정 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)

        return {"text": f"판정 실패: {e}", "success": False}


async def regenerate_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    재생성 준비 노드 (GraphBuilder 호환).

    평가 결과에서 피드백을 수집하고 번역기에 전달할 형태로 포맷합니다.
    """
    try:
        state = get_workflow_state()
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

        logger.info(
            f"[{unit.key}] 피드백: "
            f"{len(feedback.previous_issues)}개 이슈, "
            f"{len(feedback.corrections)}개 수정"
        )

        return {"text": "재생성 준비 완료", "success": True}

    except Exception as e:
        logger.error(f"재생성 준비 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)

        return {"text": f"재생성 실패: {e}", "success": False}


async def finalize_node(task=None, **kwargs) -> Dict[str, Any]:
    """
    최종 상태 설정 노드 (GraphBuilder 호환).

    판정 결과에 따라 최종 워크플로우 상태를 설정합니다.
    """
    try:
        state = get_workflow_state()
        unit: TranslationUnit = state["unit"]
        decision: GateDecision = state["gate_decision"]
        translation_result: TranslationResult = state["translation_result"]

        if decision.verdict == Verdict.PASS:
            state["workflow_state"] = WorkflowState.PUBLISHED
            state["final_translation"] = translation_result.translation
            logger.info(f"[{unit.key}] 발행 완료")
            result_text = "발행 완료"

        elif decision.verdict == Verdict.BLOCK:
            state["workflow_state"] = WorkflowState.REJECTED
            logger.warning(f"[{unit.key}] 거부됨")
            result_text = "거부됨"

        elif decision.verdict == Verdict.ESCALATE:
            state["workflow_state"] = WorkflowState.PENDING_REVIEW
            logger.info(f"[{unit.key}] PM 검수 대기")
            result_text = "PM 검수 대기"

        elif decision.verdict == Verdict.REGENERATE:
            # 최대 재생성 횟수 초과 시 REJECTED로 전환
            state["workflow_state"] = WorkflowState.REJECTED
            logger.warning(f"[{unit.key}] 재생성 횟수 초과로 거부됨")
            result_text = "재생성 횟수 초과로 거부됨"

        else:
            state["workflow_state"] = WorkflowState.FAILED
            logger.error(f"[{unit.key}] 알 수 없는 판정: {decision.verdict}")
            result_text = f"알 수 없는 판정: {decision.verdict}"

        return {"text": result_text, "success": True}

    except Exception as e:
        logger.error(f"최종화 실패: {e}")
        state = get_workflow_state()
        state["workflow_state"] = WorkflowState.FAILED
        state["error"] = str(e)

        return {"text": f"최종화 실패: {e}", "success": False}


# =============================================================================
# GraphBuilder 조건 함수
# =============================================================================

def should_regenerate(_) -> bool:
    """
    재생성 조건 확인 (GraphBuilder 조건 함수).

    decide 노드 후 regenerate 또는 finalize로 분기할 때 사용합니다.
    """
    try:
        state = get_workflow_state()
        decision = state.get("gate_decision")
        max_regen = state.get("max_regenerations", 1)
        attempt = state.get("attempt_count", 1)

        # 재생성 판정이면서 아직 최대 횟수에 도달하지 않은 경우
        if decision and decision.verdict == Verdict.REGENERATE:
            if attempt <= max_regen:
                logger.info(f"should_regenerate: True (시도 {attempt}/{max_regen})")
                return True

        logger.info("should_regenerate: False")
        return False
    except Exception as e:
        logger.warning(f"should_regenerate 오류: {e}")
        return False


def should_finalize(_) -> bool:
    """
    최종화 조건 확인 (GraphBuilder 조건 함수).

    should_regenerate의 반대 조건입니다.
    """
    return not should_regenerate(_)


__all__ = [
    # 노드 함수
    "translate_node",
    "backtranslate_node",
    "evaluate_node",
    "decide_node",
    "regenerate_node",
    "finalize_node",
    # 조건 함수
    "should_regenerate",
    "should_finalize",
]
