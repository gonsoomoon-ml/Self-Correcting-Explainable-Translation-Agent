"""
Data models for the translation agent workflow
"""

from .translation_unit import TranslationUnit
from .agent_result import AgentResult, Correction
from .gate_decision import GateDecision, Verdict
from .workflow_state import WorkflowState, is_terminal_state, can_transition, VALID_TRANSITIONS
from .translation_record import TranslationRecord, PMReview
from .tool_results import TranslationResult, BacktranslationResult

__all__ = [
    # Translation unit
    "TranslationUnit",

    # Agent results
    "AgentResult",
    "Correction",

    # Gate decision
    "GateDecision",
    "Verdict",

    # Workflow state
    "WorkflowState",
    "is_terminal_state",
    "can_transition",
    "VALID_TRANSITIONS",

    # Translation record
    "TranslationRecord",
    "PMReview",

    # Tool results
    "TranslationResult",
    "BacktranslationResult",
]
