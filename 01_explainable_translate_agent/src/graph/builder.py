"""
워크플로우 그래프 빌더 - 번역 파이프라인 오케스트레이션

State Machine 기반으로 조건부 라우팅을 구현합니다.

워크플로우 흐름:
    INIT → TRANSLATE → BACKTRANSLATE → EVALUATE → DECIDE
                                                     ↓
                                    ┌────────────────┼────────────────┐
                                    ↓                ↓                ↓
                                 PUBLISHED      REGENERATE        REJECTED
                                              (loop back)       /ESCALATE
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from src.models.translation_unit import TranslationUnit
from src.models.translation_record import TranslationRecord
from src.models.gate_decision import Verdict
from src.models.workflow_state import WorkflowState, is_terminal_state
from src.graph.nodes import (
    translate_node,
    backtranslate_node,
    evaluate_node,
    decide_node,
    regenerate_node,
    finalize_node
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """워크플로우 설정"""
    max_regenerations: int = 1          # 최대 재생성 횟수
    num_candidates: int = 1             # 번역 후보 수
    enable_backtranslation: bool = True # 역번역 활성화
    timeout_seconds: int = 120          # 전체 타임아웃


@dataclass
class WorkflowMetrics:
    """워크플로우 메트릭"""
    total_latency_ms: int = 0
    translation_latency_ms: int = 0
    backtranslation_latency_ms: int = 0
    evaluation_latency_ms: int = 0
    attempt_count: int = 1
    token_usage: Dict[str, int] = field(default_factory=dict)


def should_regenerate(state: Dict[str, Any]) -> bool:
    """재생성 조건 확인"""
    decision = state.get("gate_decision")
    return decision and decision.verdict == Verdict.REGENERATE


def should_finalize(state: Dict[str, Any]) -> bool:
    """최종화 조건 확인 (PASS, BLOCK, ESCALATE)"""
    decision = state.get("gate_decision")
    if not decision:
        return False
    return decision.verdict in [Verdict.PASS, Verdict.BLOCK, Verdict.ESCALATE]


def is_failed(state: Dict[str, Any]) -> bool:
    """실패 상태 확인"""
    return state.get("workflow_state") == WorkflowState.FAILED


class TranslationWorkflowGraph:
    """
    번역 워크플로우 그래프.

    State Machine 패턴으로 번역 파이프라인을 오케스트레이션합니다.

    흐름:
    1. 번역 생성 (Translator)
    2. 역번역 (Backtranslator)
    3. 병렬 평가 (3 Evaluators)
    4. 판정 (Release Guard)
    5. 라우팅:
       - PASS → 발행
       - REGENERATE → 피드백 수집 후 1로 돌아감
       - BLOCK/ESCALATE → 거부 또는 PM 검수

    사용 예:
        graph = TranslationWorkflowGraph()
        result = await graph.run(translation_unit)
        print(result["workflow_state"])  # PUBLISHED, REJECTED, etc.
    """

    def __init__(self, config: Optional[WorkflowConfig] = None):
        """
        워크플로우 그래프 초기화.

        Args:
            config: 워크플로우 설정. 미제공시 기본값 사용.
        """
        self.config = config or WorkflowConfig()

    async def run(self, unit: TranslationUnit) -> Dict[str, Any]:
        """
        워크플로우 실행.

        Args:
            unit: 번역할 TranslationUnit

        Returns:
            최종 워크플로우 상태 딕셔너리:
                - unit: 입력 TranslationUnit
                - translation_result: 번역 결과
                - backtranslation_result: 역번역 결과
                - agent_results: 평가 결과 리스트
                - gate_decision: 최종 판정
                - workflow_state: 최종 상태
                - final_translation: 최종 번역 (PASS인 경우)
                - attempt_count: 총 시도 횟수
                - metrics: WorkflowMetrics
        """
        start_time = datetime.now()

        # 초기 상태 설정
        state = {
            "unit": unit,
            "attempt_count": 1,
            "num_candidates": self.config.num_candidates,
            "max_regenerations": self.config.max_regenerations,
            "workflow_state": WorkflowState.INITIALIZED,
            "created_at": start_time
        }

        logger.info(f"워크플로우 시작: {unit.key}")

        try:
            state = await self._run_pipeline(state)
        except Exception as e:
            logger.error(f"워크플로우 실패: {e}")
            state["workflow_state"] = WorkflowState.FAILED
            state["error"] = str(e)

        # 메트릭 계산
        end_time = datetime.now()
        state["metrics"] = self._calculate_metrics(state, start_time, end_time)

        logger.info(
            f"워크플로우 완료: {state['workflow_state'].value} "
            f"(시도 {state.get('attempt_count', 1)}회, "
            f"{state['metrics'].total_latency_ms}ms)"
        )

        return state

    async def _run_pipeline(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        메인 파이프라인 루프.

        Maker-Checker 패턴으로 필요시 재생성합니다.
        """
        while True:
            # Step 1: 번역
            state = await translate_node(state)
            if is_failed(state):
                break

            # Step 2: 역번역
            if self.config.enable_backtranslation:
                state = await backtranslate_node(state)
                if is_failed(state):
                    break

            # Step 3: 평가
            state = await evaluate_node(state)
            if is_failed(state):
                break

            # Step 4: 판정
            state = await decide_node(state)
            if is_failed(state):
                break

            # Step 5: 라우팅
            if should_finalize(state):
                state = await finalize_node(state)
                break

            if should_regenerate(state):
                # 최대 재생성 횟수 확인
                if state.get("attempt_count", 1) > self.config.max_regenerations:
                    logger.warning("최대 재생성 횟수 초과")
                    state = await finalize_node(state)
                    break

                # 재생성 준비 후 루프 계속
                state = await regenerate_node(state)
                continue

            # 예상치 못한 상태
            logger.error(f"예상치 못한 판정: {state.get('gate_decision')}")
            state["workflow_state"] = WorkflowState.FAILED
            break

        return state

    def _calculate_metrics(
        self,
        state: Dict[str, Any],
        start_time: datetime,
        end_time: datetime
    ) -> WorkflowMetrics:
        """워크플로우 메트릭 계산"""
        total_latency = int((end_time - start_time).total_seconds() * 1000)

        # 개별 단계 지연시간
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

    async def run_batch(
        self,
        units: list[TranslationUnit],
        concurrency: int = 5
    ) -> list[Dict[str, Any]]:
        """
        배치 워크플로우 실행.

        여러 TranslationUnit을 동시에 처리합니다.

        Args:
            units: 번역할 TranslationUnit 리스트
            concurrency: 동시 처리 수

        Returns:
            각 unit의 워크플로우 결과 리스트
        """
        import asyncio
        from asyncio import Semaphore

        semaphore = Semaphore(concurrency)

        async def run_with_semaphore(unit: TranslationUnit) -> Dict[str, Any]:
            async with semaphore:
                return await self.run(unit)

        logger.info(f"배치 처리 시작: {len(units)}개 항목, 동시성 {concurrency}")

        results = await asyncio.gather(
            *[run_with_semaphore(unit) for unit in units],
            return_exceptions=True
        )

        # 예외를 실패 결과로 변환
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "unit": units[i],
                    "workflow_state": WorkflowState.FAILED,
                    "error": str(result)
                })
            else:
                processed_results.append(result)

        # 통계 로깅
        states = [r.get("workflow_state", WorkflowState.FAILED) for r in processed_results]
        published = sum(1 for s in states if s == WorkflowState.PUBLISHED)
        rejected = sum(1 for s in states if s == WorkflowState.REJECTED)
        failed = sum(1 for s in states if s == WorkflowState.FAILED)

        logger.info(
            f"배치 처리 완료: 발행 {published}, 거부 {rejected}, 실패 {failed}"
        )

        return processed_results
