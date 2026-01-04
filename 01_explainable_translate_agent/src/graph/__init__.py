"""
번역 워크플로우 그래프

State Machine 기반 번역 파이프라인 오케스트레이션.

사용 예:
    from src.graph import TranslationWorkflowGraph, WorkflowConfig
    from src.models import TranslationUnit

    # 기본 설정으로 실행
    graph = TranslationWorkflowGraph()
    result = await graph.run(unit)

    # 커스텀 설정으로 실행
    config = WorkflowConfig(max_regenerations=2, num_candidates=2)
    graph = TranslationWorkflowGraph(config)
    result = await graph.run(unit)

    # 배치 처리
    results = await graph.run_batch(units, concurrency=10)
"""

# 그래프 빌더
from src.graph.builder import (
    TranslationWorkflowGraph,
    WorkflowConfig,
    WorkflowMetrics
)

# 개별 노드 (고급 사용자용)
from src.graph.nodes import (
    translate_node,
    backtranslate_node,
    evaluate_node,
    decide_node,
    regenerate_node,
    finalize_node
)

__all__ = [
    # 메인 API
    "TranslationWorkflowGraph",
    "WorkflowConfig",
    "WorkflowMetrics",
    # 노드 (고급)
    "translate_node",
    "backtranslate_node",
    "evaluate_node",
    "decide_node",
    "regenerate_node",
    "finalize_node",
]
