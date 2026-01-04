"""
Gate Decision - Release gate verdict schema
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum


class Verdict(str, Enum):
    """Possible gate verdicts"""
    PASS = "pass"           # All agents passed (score >= 4)
    BLOCK = "block"         # Any agent failed (score <= 2)
    REGENERATE = "regenerate"  # Borderline (score = 3), retry allowed
    ESCALATE = "escalate"   # Placeholder (HITL not implemented) - treated as BLOCK


class GateDecision(BaseModel):
    """평가 게이트 판정 결과 - Release gate decision"""

    # Final verdict
    verdict: Verdict = Field(..., description="Gate verdict")
    can_publish: bool = Field(..., description="Whether translation can be published")

    # Score information
    scores: Dict[str, int] = Field(
        ...,
        description="Scores by agent (accuracy, compliance, quality)"
    )
    min_score: int = Field(..., description="Minimum score across all agents")
    avg_score: float = Field(..., description="Average score across all agents")

    # Chain-of-Thought (for explainability)
    reasoning_chains: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Reasoning chains by agent name"
    )

    # Details
    blocker_agent: Optional[str] = Field(
        default=None,
        description="Agent that caused BLOCK verdict (if any)"
    )
    review_agents: List[str] = Field(
        default_factory=list,
        description="Agents that require review (score = 3)"
    )
    corrections: List[dict] = Field(
        default_factory=list,
        description="All suggested corrections from agents"
    )
    message: str = Field(
        default="",
        description="Human-readable summary of the decision"
    )

    # Metrics
    agent_agreement_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agreement score between agents (0-1)"
    )
    total_latency_ms: int = Field(
        default=0,
        description="Total evaluation latency in milliseconds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "verdict": "pass",
                "can_publish": True,
                "scores": {
                    "accuracy": 5,
                    "compliance": 4,
                    "quality": 4
                },
                "min_score": 4,
                "avg_score": 4.33,
                "reasoning_chains": {
                    "accuracy": ["Step 1: Semantic check passed", "Step 2: Glossary verified"],
                    "compliance": ["Step 1: No prohibited terms found"],
                    "quality": ["Step 1: Tone appropriate for US market"]
                },
                "blocker_agent": None,
                "review_agents": [],
                "corrections": [],
                "message": "All agents passed. Ready for publishing.",
                "agent_agreement_score": 0.95,
                "total_latency_ms": 3500
            }
        }
