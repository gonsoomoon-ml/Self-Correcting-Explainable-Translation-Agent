"""
Workflow State - State machine definition for translation pipeline

Used with Strands Agent for workflow state tracking and validation.
"""

from enum import Enum, auto


class WorkflowState(str, Enum):
    """Translation workflow states"""

    # Initial states
    INITIALIZED = "initialized"       # Workflow initialized, ready to start

    # Processing states
    TRANSLATING = "translating"       # Translation in progress
    BACKTRANSLATING = "backtranslating"  # Back-translation for verification
    EVALUATING = "evaluating"         # 3 agents evaluating in parallel
    DECIDING = "deciding"             # Release guard making decision

    # Loop states
    REGENERATING = "regenerating"     # Maker-Checker loop: regenerating with feedback

    # HITL states (placeholder - not implemented)
    PENDING_REVIEW = "pending_review" # Placeholder for future HITL
    APPROVED = "approved"             # Placeholder for future HITL

    # Terminal states
    REJECTED = "rejected"             # Translation rejected/blocked
    PUBLISHED = "published"           # Translation published successfully
    FAILED = "failed"                 # Workflow failed due to error


# State transition rules
VALID_TRANSITIONS = {
    WorkflowState.INITIALIZED: [WorkflowState.TRANSLATING, WorkflowState.FAILED],
    WorkflowState.TRANSLATING: [WorkflowState.BACKTRANSLATING, WorkflowState.FAILED],
    WorkflowState.BACKTRANSLATING: [WorkflowState.EVALUATING, WorkflowState.FAILED],
    WorkflowState.EVALUATING: [WorkflowState.DECIDING, WorkflowState.FAILED],
    WorkflowState.DECIDING: [
        WorkflowState.PUBLISHED,      # All pass -> publish
        WorkflowState.REGENERATING,   # Borderline -> retry
        WorkflowState.REJECTED,       # Fail or escalate (HITL not implemented)
        WorkflowState.FAILED
    ],
    WorkflowState.REGENERATING: [WorkflowState.EVALUATING, WorkflowState.FAILED],
    # HITL transitions (placeholder - not implemented)
    WorkflowState.PENDING_REVIEW: [WorkflowState.REJECTED, WorkflowState.FAILED],
    WorkflowState.APPROVED: [WorkflowState.PUBLISHED],
    # Terminal states
    WorkflowState.REJECTED: [],
    WorkflowState.PUBLISHED: [],
    WorkflowState.FAILED: [],
}


def is_terminal_state(state: WorkflowState) -> bool:
    """Check if a state is terminal (no further transitions)"""
    return state in [
        WorkflowState.REJECTED,
        WorkflowState.PUBLISHED,
        WorkflowState.FAILED
    ]


def can_transition(from_state: WorkflowState, to_state: WorkflowState) -> bool:
    """Check if a state transition is valid"""
    return to_state in VALID_TRANSITIONS.get(from_state, [])
