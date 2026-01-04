"""
Translation Record - Complete translation workflow record for storage
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from .translation_unit import TranslationUnit
from .agent_result import AgentResult
from .gate_decision import GateDecision
from .workflow_state import WorkflowState


class PMReview(BaseModel):
    """PM review feedback (placeholder for future HITL implementation)"""
    pass


class TranslationRecord(BaseModel):
    """번역 전체 기록 - Complete translation workflow record"""

    # Identifiers
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique record ID"
    )
    unit: TranslationUnit = Field(..., description="Translation unit input")

    # Translation data
    candidates: List[str] = Field(
        default_factory=list,
        description="1-2 translation candidates"
    )
    selected_candidate: int = Field(
        default=0,
        description="Index of selected candidate"
    )
    backtranslation: str = Field(
        default="",
        description="Back-translation to source language"
    )
    final_translation: str = Field(
        default="",
        description="Final approved translation"
    )

    # Evaluation results
    agent_results: List[AgentResult] = Field(
        default_factory=list,
        description="Results from 3 evaluation agents"
    )
    gate_decision: Optional[GateDecision] = Field(
        default=None,
        description="Release gate decision"
    )

    # Workflow information
    attempt_count: int = Field(
        default=1,
        description="Number of translation attempts"
    )
    workflow_state: WorkflowState = Field(
        default=WorkflowState.INITIALIZED,
        description="Current workflow state"
    )

    # PM review (if escalated)
    pm_review: Optional[PMReview] = Field(
        default=None,
        description="PM review if HITL escalation occurred"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )
    published_at: Optional[datetime] = Field(
        default=None,
        description="Publication timestamp (if published)"
    )

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., batch_id, requester)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "unit": {
                    "key": "IDS_FAQ_SC_ABOUT",
                    "source_text": "ABC 클라우드는 서비스입니다.",
                    "source_lang": "ko",
                    "target_lang": "en-rUS"
                },
                "candidates": [
                    "ABC Cloud is a service.",
                    "ABC Cloud provides a service."
                ],
                "selected_candidate": 0,
                "backtranslation": "ABC 클라우드는 서비스입니다.",
                "final_translation": "ABC Cloud is a service.",
                "attempt_count": 1,
                "workflow_state": "published",
                "created_at": "2025-01-03T10:00:00Z",
                "published_at": "2025-01-03T10:05:00Z"
            }
        }
