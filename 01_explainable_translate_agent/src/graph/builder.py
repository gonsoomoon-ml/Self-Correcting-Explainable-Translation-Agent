"""
Strands GraphBuilder 기반 워크플로우 빌더

기존 builder.py의 기능을 Strands GraphBuilder로 재구현합니다.

주요 변경사항:
- 선언적 그래프 정의 (add_node, add_edge)
- 조건부 엣지 (condition 파라미터)
- FunctionNode 래퍼 사용

워크플로우 흐름:
    TRANSLATE → BACKTRANSLATE → EVALUATE → DECIDE
                                              ↓
                              ┌───────────────┼───────────────┐
                              ↓               ↓               ↓
                          FINALIZE       REGENERATE      FINALIZE
                         (PASS/BLOCK)   (loop back)    (ESCALATE)

사용법:
    from src.graph.builder import build_translation_graph, TranslationWorkflowConfig

    # 그래프 빌드
    config = TranslationWorkflowConfig(max_regenerations=2)
    graph = build_translation_graph(config)

    # 실행
    from src.utils import workflow_context, get_workflow_state

    with workflow_context(unit, config) as workflow_id:
        result = await graph.invoke_async({"unit": unit})
        final_state = get_workflow_state(workflow_id)
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from strands.multiagent import GraphBuilder

from src.models.translation_unit import TranslationUnit
from src.models.workflow_state import WorkflowState
from src.utils.strands_utils import FunctionNode
from src.utils.workflow_state import (
    WorkflowConfig,
    WorkflowStateManager,
    get_state_manager,
    get_workflow_state,
    workflow_context,
)
from src.graph.nodes import (
    translate_node,
    backtranslate_node,
    evaluate_node,
    decide_node,
    regenerate_node,
    finalize_node,
    should_regenerate,
    should_finalize,
)

logger = logging.getLogger(__name__)


@dataclass
class TranslationWorkflowConfig:
    """번역 워크플로우 설정"""
    max_regenerations: int = 1
    num_candidates: int = 1
    enable_backtranslation: bool = True
    timeout_seconds: int = 120
    max_node_executions: int = 15  # 무한 루프 방지


@dataclass
class WorkflowMetrics:
    """워크플로우 메트릭"""
    total_latency_ms: int = 0
    translation_latency_ms: int = 0
    backtranslation_latency_ms: int = 0
    evaluation_latency_ms: int = 0
    attempt_count: int = 1
    token_usage: Dict[str, int] = field(default_factory=dict)


def build_translation_graph(
    config: Optional[TranslationWorkflowConfig] = None
):
    """
    Strands GraphBuilder로 번역 워크플로우 그래프 빌드.

    Args:
        config: 워크플로우 설정

    Returns:
        Graph: Strands Graph 인스턴스

    Example:
        graph = build_translation_graph(TranslationWorkflowConfig(max_regenerations=2))

        with workflow_context(unit) as wf_id:
            result = await graph.invoke_async({"key": unit.key})
            state = get_workflow_state(wf_id)
    """
    config = config or TranslationWorkflowConfig()
    builder = GraphBuilder()

    # ==========================================================================
    # 노드 등록
    # ==========================================================================
    # 기존 노드 함수를 FunctionNode로 래핑
    builder.add_node(FunctionNode(translate_node, "translate"), "translate")
    builder.add_node(FunctionNode(backtranslate_node, "backtranslate"), "backtranslate")
    builder.add_node(FunctionNode(evaluate_node, "evaluate"), "evaluate")
    builder.add_node(FunctionNode(decide_node, "decide"), "decide")
    builder.add_node(FunctionNode(regenerate_node, "regenerate"), "regenerate")
    builder.add_node(FunctionNode(finalize_node, "finalize"), "finalize")

    # ==========================================================================
    # 엣지 정의 (워크플로우 흐름)
    # ==========================================================================
    builder.set_entry_point("translate")

    # 메인 파이프라인: translate → backtranslate → evaluate → decide
    if config.enable_backtranslation:
        builder.add_edge("translate", "backtranslate")
        builder.add_edge("backtranslate", "evaluate")
    else:
        builder.add_edge("translate", "evaluate")

    builder.add_edge("evaluate", "decide")

    # 조건부 분기: decide → finalize 또는 regenerate
    builder.add_edge("decide", "finalize", condition=should_finalize)
    builder.add_edge("decide", "regenerate", condition=should_regenerate)

    # 재생성 루프: regenerate → translate
    builder.add_edge("regenerate", "translate")

    # ==========================================================================
    # 실행 제한
    # ==========================================================================
    # 무한 루프 방지: max_regenerations + 기본 실행 횟수
    max_executions = config.max_node_executions
    builder.set_max_node_executions(max_executions)

    if config.timeout_seconds > 0:
        builder.set_execution_timeout(config.timeout_seconds)

    logger.info(
        f"번역 그래프 빌드 완료 - "
        f"max_regenerations: {config.max_regenerations}, "
        f"max_node_executions: {max_executions}"
    )

    return builder.build()


class TranslationWorkflowGraphV2:
    """
    Strands GraphBuilder 기반 번역 워크플로우 그래프.

    기존 TranslationWorkflowGraph와 호환되는 인터페이스를 제공하면서
    내부적으로는 Strands GraphBuilder를 사용합니다.

    Example:
        graph = TranslationWorkflowGraphV2(config)
        result = await graph.run(unit)
        print(result["workflow_state"])
    """

    def __init__(self, config: Optional[TranslationWorkflowConfig] = None):
        """
        워크플로우 그래프 초기화.

        Args:
            config: 워크플로우 설정
        """
        self.config = config or TranslationWorkflowConfig()
        self.graph = build_translation_graph(self.config)
        self.state_manager = get_state_manager()

    async def run(self, unit: TranslationUnit) -> Dict[str, Any]:
        """
        워크플로우 실행.

        기존 TranslationWorkflowGraph.run()과 동일한 인터페이스.

        Args:
            unit: 번역할 TranslationUnit

        Returns:
            최종 워크플로우 상태 딕셔너리
        """
        start_time = datetime.now()

        # 워크플로우 상태 생성
        workflow_config = WorkflowConfig(
            max_regenerations=self.config.max_regenerations,
            num_candidates=self.config.num_candidates,
            enable_backtranslation=self.config.enable_backtranslation,
            timeout_seconds=self.config.timeout_seconds
        )
        workflow_id = self.state_manager.create_workflow(unit, workflow_config)

        logger.info(f"워크플로우 시작: {unit.key} (workflow_id: {workflow_id})")

        try:
            # GraphBuilder 실행
            task = {"key": unit.key}
            await self.graph.invoke_async(task)

            # 최종 상태 가져오기
            state = self.state_manager.get_state(workflow_id)

        except Exception as e:
            logger.error(f"워크플로우 실패: {e}")
            state = self.state_manager.get_state(workflow_id)
            state["workflow_state"] = WorkflowState.FAILED
            state["error"] = str(e)

        # 메트릭 계산
        end_time = datetime.now()
        state["metrics"] = self._calculate_metrics(state, start_time, end_time)

        # 정리
        final_state = self.state_manager.cleanup(workflow_id)

        logger.info(
            f"워크플로우 완료: {final_state.get('workflow_state', WorkflowState.FAILED).value} "
            f"(시도 {final_state.get('attempt_count', 1)}회, "
            f"{final_state.get('metrics', {}).total_latency_ms if hasattr(final_state.get('metrics', {}), 'total_latency_ms') else 0}ms)"
        )

        return final_state

    def _calculate_metrics(
        self,
        state: Dict[str, Any],
        start_time: datetime,
        end_time: datetime
    ) -> WorkflowMetrics:
        """워크플로우 메트릭 계산 (기존 로직 유지)"""
        total_latency = int((end_time - start_time).total_seconds() * 1000)

        translation_latency = 0
        backtranslation_latency = 0
        evaluation_latency = 0
        token_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

        if "translation_result" in state:
            tr = state["translation_result"]
            translation_latency = tr.latency_ms
            if tr.token_usage:
                token_usage["input"] += tr.token_usage.get("input_tokens", 0)
                token_usage["output"] += tr.token_usage.get("output_tokens", 0)
                token_usage["cache_read"] += tr.token_usage.get("cache_read_input_tokens", 0)
                token_usage["cache_write"] += tr.token_usage.get("cache_write_input_tokens", 0)

        if "backtranslation_result" in state:
            bt = state["backtranslation_result"]
            backtranslation_latency = bt.latency_ms
            if bt.token_usage:
                token_usage["input"] += bt.token_usage.get("input_tokens", 0)
                token_usage["output"] += bt.token_usage.get("output_tokens", 0)
                token_usage["cache_read"] += bt.token_usage.get("cache_read_input_tokens", 0)
                token_usage["cache_write"] += bt.token_usage.get("cache_write_input_tokens", 0)

        if "agent_results" in state:
            for ar in state["agent_results"]:
                evaluation_latency += ar.latency_ms
                if ar.token_usage:
                    token_usage["input"] += ar.token_usage.get("input_tokens", 0)
                    token_usage["output"] += ar.token_usage.get("output_tokens", 0)
                    token_usage["cache_read"] += ar.token_usage.get("cache_read_input_tokens", 0)
                    token_usage["cache_write"] += ar.token_usage.get("cache_write_input_tokens", 0)

        return WorkflowMetrics(
            total_latency_ms=total_latency,
            translation_latency_ms=translation_latency,
            backtranslation_latency_ms=backtranslation_latency,
            evaluation_latency_ms=evaluation_latency,
            attempt_count=state.get("attempt_count", 1),
            token_usage=token_usage
        )


__all__ = [
    "TranslationWorkflowConfig",
    "WorkflowMetrics",
    "build_translation_graph",
    "TranslationWorkflowGraphV2",
]
