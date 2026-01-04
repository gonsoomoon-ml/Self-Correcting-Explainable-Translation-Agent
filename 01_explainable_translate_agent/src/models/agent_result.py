"""
Agent Result - Evaluation agent output schema
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Literal


class Correction(BaseModel):
    """Suggested correction for identified issues"""

    original: str = Field(..., description="Original text with issue")
    suggested: str = Field(..., description="Suggested replacement")
    reason: str = Field(..., description="Reason for the correction")


class AgentResult(BaseModel):
    """평가 에이전트 결과 - Evaluation agent output"""

    # Agent identification
    agent_name: str = Field(
        ...,
        description="Agent name: accuracy, compliance, or quality"
    )

    # Chain-of-Thought (evaluation process)
    reasoning_chain: List[str] = Field(
        default_factory=list,
        description="Step-by-step analysis results for explainability"
    )

    # Final verdict
    score: int = Field(
        ...,
        ge=0,
        le=5,
        description="Score from 0-5 scale"
    )
    verdict: Literal["pass", "fail", "review"] = Field(
        ...,
        description="pass (score>=4), fail (score<=2), review (score=3)"
    )

    # Details
    issues: List[str] = Field(
        default_factory=list,
        description="List of identified issues"
    )
    corrections: List[Correction] = Field(
        default_factory=list,
        description="Suggested corrections"
    )

    # Metadata
    token_usage: Dict[str, int] = Field(
        default_factory=dict,
        description="Token usage stats (input_tokens, output_tokens)"
    )
    latency_ms: int = Field(
        default=0,
        description="Response time in milliseconds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "agent_name": "accuracy",
                "reasoning_chain": [
                    "Step 1: Checking semantic preservation - Source meaning intact",
                    "Step 2: Verifying glossary terms - 'ABC Cloud' correctly used",
                    "Step 3: Comparing with back-translation - High similarity score"
                ],
                "score": 4,
                "verdict": "pass",
                "issues": [],
                "corrections": [],
                "token_usage": {"input_tokens": 500, "output_tokens": 150},
                "latency_ms": 1200
            }
        }
