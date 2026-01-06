"""
워크플로우 상태 관리 - GraphBuilder 노드 간 상태 공유

Strands GraphBuilder에서 노드 간 데이터를 공유하기 위한 글로벌 상태 관리자.
기존 Dict 기반 상태 전달 패턴을 글로벌 상태 패턴으로 전환합니다.



주요 기능:
- 워크플로우 인스턴스별 격리된 상태 관리
- 스레드 안전 접근
- 기존 노드 코드와의 호환성 유지

Example:
    from src.utils.workflow_state import WorkflowStateManager

    # 워크플로우 시작 시
    state_manager = WorkflowStateManager()
    workflow_id = state_manager.create_workflow(unit, config)

    # 노드에서 상태 접근
    state = state_manager.get_state(workflow_id)
    state["translation_result"] = result

    # 워크플로우 종료 시
    final_state = state_manager.get_state(workflow_id)
    state_manager.cleanup(workflow_id)
"""

import uuid
import threading
from typing import Any, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, field
from contextlib import contextmanager

from src.models.workflow_state import WorkflowState


# =============================================================================
# 글로벌 상태 저장소
# =============================================================================

# 워크플로우 ID → 상태 매핑
_workflow_states: Dict[str, Dict[str, Any]] = {}
_states_lock = threading.Lock()

# 현재 활성 워크플로우 ID (단일 워크플로우 실행 시 편의용)
_current_workflow_id: Optional[str] = None


@dataclass
class WorkflowConfig:
    """워크플로우 설정 (GraphBuilder용)"""
    max_regenerations: int = 1
    num_candidates: int = 1
    enable_backtranslation: bool = True
    timeout_seconds: int = 120


class WorkflowStateManager:
    """
    워크플로우 상태 관리자.

    여러 동시 워크플로우의 상태를 격리하여 관리합니다.
    배치 처리 시 각 워크플로우가 독립적인 상태를 가질 수 있습니다.

    Example:
        manager = WorkflowStateManager()

        # 워크플로우 생성
        wf_id = manager.create_workflow(unit, config)

        # 상태 접근
        state = manager.get_state(wf_id)
        state["translation_result"] = result

        # 정리
        manager.cleanup(wf_id)
    """

    def create_workflow(
        self,
        unit: Any,
        config: Optional[WorkflowConfig] = None
    ) -> str:
        """
        새 워크플로우 상태 생성.

        Args:
            unit: TranslationUnit 인스턴스
            config: 워크플로우 설정

        Returns:
            워크플로우 ID
        """
        global _current_workflow_id

        workflow_id = str(uuid.uuid4())
        config = config or WorkflowConfig()

        initial_state = {
            "workflow_id": workflow_id,
            "unit": unit,
            "attempt_count": 1,
            "num_candidates": config.num_candidates,
            "max_regenerations": config.max_regenerations,
            "workflow_state": WorkflowState.INITIALIZED,
            "created_at": datetime.now(),
            # 토큰 추적용
            "token_usage": {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "by_agent": {}
            }
        }

        with _states_lock:
            _workflow_states[workflow_id] = initial_state
            _current_workflow_id = workflow_id

        return workflow_id

    def get_state(self, workflow_id: Optional[str] = None) -> Dict[str, Any]:
        """
        워크플로우 상태 가져오기.

        Args:
            workflow_id: 워크플로우 ID (없으면 현재 활성 워크플로우)

        Returns:
            상태 딕셔너리 (직접 수정 가능)

        Raises:
            ValueError: 워크플로우를 찾을 수 없는 경우
        """
        wf_id = workflow_id or _current_workflow_id

        if not wf_id:
            raise ValueError("활성 워크플로우가 없습니다. create_workflow()를 먼저 호출하세요.")

        with _states_lock:
            if wf_id not in _workflow_states:
                raise ValueError(f"워크플로우를 찾을 수 없음: {wf_id}")
            return _workflow_states[wf_id]

    def update_state(
        self,
        updates: Dict[str, Any],
        workflow_id: Optional[str] = None
    ) -> None:
        """
        워크플로우 상태 업데이트.

        Args:
            updates: 업데이트할 키-값 쌍
            workflow_id: 워크플로우 ID (없으면 현재 활성 워크플로우)
        """
        state = self.get_state(workflow_id)
        state.update(updates)

    def cleanup(self, workflow_id: Optional[str] = None) -> Dict[str, Any]:
        """
        워크플로우 상태 정리 및 반환.

        Args:
            workflow_id: 워크플로우 ID (없으면 현재 활성 워크플로우)

        Returns:
            정리된 최종 상태
        """
        global _current_workflow_id

        wf_id = workflow_id or _current_workflow_id

        if not wf_id:
            return {}

        with _states_lock:
            final_state = _workflow_states.pop(wf_id, {})
            if _current_workflow_id == wf_id:
                _current_workflow_id = None

        return final_state

    def get_current_workflow_id(self) -> Optional[str]:
        """현재 활성 워크플로우 ID 반환."""
        return _current_workflow_id

    def list_workflows(self) -> list:
        """모든 활성 워크플로우 ID 목록 반환."""
        with _states_lock:
            return list(_workflow_states.keys())


# 싱글톤 인스턴스
_state_manager: Optional[WorkflowStateManager] = None


def get_state_manager() -> WorkflowStateManager:
    """싱글톤 상태 관리자 가져오기."""
    global _state_manager
    if _state_manager is None:
        _state_manager = WorkflowStateManager()
    return _state_manager


# =============================================================================
# 편의 함수 - 노드에서 직접 사용
# =============================================================================

def get_workflow_state(workflow_id: Optional[str] = None) -> Dict[str, Any]:
    """
    현재 워크플로우 상태 가져오기.

    노드 함수에서 직접 호출하여 상태에 접근합니다.

    Example:
        async def translate_node(task=None, **kwargs):
            state = get_workflow_state()
            unit = state["unit"]
            # ... 번역 로직
            state["translation_result"] = result
            return {"text": "번역 완료"}
    """
    return get_state_manager().get_state(workflow_id)


def update_workflow_state(
    updates: Dict[str, Any],
    workflow_id: Optional[str] = None
) -> None:
    """
    현재 워크플로우 상태 업데이트.

    Example:
        update_workflow_state({
            "translation_result": result,
            "workflow_state": WorkflowState.TRANSLATING
        })
    """
    get_state_manager().update_state(updates, workflow_id)


@contextmanager
def workflow_context(unit: Any, config: Optional[WorkflowConfig] = None):
    """
    워크플로우 컨텍스트 매니저.

    워크플로우 생성, 실행, 정리를 자동으로 처리합니다.

    Example:
        with workflow_context(unit, config) as workflow_id:
            result = await graph.invoke_async(task)
            final_state = get_workflow_state(workflow_id)
    """
    manager = get_state_manager()
    workflow_id = manager.create_workflow(unit, config)

    try:
        yield workflow_id
    finally:
        manager.cleanup(workflow_id)


# =============================================================================
# 기존 코드 호환성 - 조건 함수용
# =============================================================================

def should_regenerate_from_state(workflow_id: Optional[str] = None) -> bool:
    """
    글로벌 상태에서 재생성 조건 확인.

    GraphBuilder 조건 함수에서 사용합니다.
    """
    from src.models.gate_decision import Verdict

    try:
        state = get_workflow_state(workflow_id)
        decision = state.get("gate_decision")
        return decision and decision.verdict == Verdict.REGENERATE
    except ValueError:
        return False


def should_finalize_from_state(workflow_id: Optional[str] = None) -> bool:
    """
    글로벌 상태에서 최종화 조건 확인.

    GraphBuilder 조건 함수에서 사용합니다.
    """
    from src.models.gate_decision import Verdict

    try:
        state = get_workflow_state(workflow_id)
        decision = state.get("gate_decision")
        if not decision:
            return False
        return decision.verdict in [Verdict.PASS, Verdict.BLOCK, Verdict.ESCALATE]
    except ValueError:
        return False


def is_workflow_failed(workflow_id: Optional[str] = None) -> bool:
    """
    워크플로우 실패 상태 확인.
    """
    try:
        state = get_workflow_state(workflow_id)
        return state.get("workflow_state") == WorkflowState.FAILED
    except ValueError:
        return False


__all__ = [
    # 클래스
    "WorkflowConfig",
    "WorkflowStateManager",
    # 싱글톤
    "get_state_manager",
    # 편의 함수
    "get_workflow_state",
    "update_workflow_state",
    "workflow_context",
    # 조건 함수
    "should_regenerate_from_state",
    "should_finalize_from_state",
    "is_workflow_failed",
]
