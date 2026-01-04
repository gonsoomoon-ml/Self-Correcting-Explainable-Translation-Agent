"""
FAQ Translation Agent

AWS Bedrock-based multi-language FAQ translation pipeline with:
- 3 evaluation agents (Accuracy, Compliance, Quality)
- Maker-Checker loop for iterative improvement
- Human-in-the-Loop for borderline cases
- 0-5 scoring scale with Pass/Fail/Regenerate logic
"""

__version__ = "0.1.0"

# Re-export key components for convenience
from .models import (
    TranslationUnit,
    AgentResult,
    GateDecision,
    Verdict,
    WorkflowState,
    TranslationRecord,
)
from .utils import (
    get_bedrock_client,
    get_config,
    get_thresholds,
)
from .prompts import (
    load_prompt,
    get_template_loader,
)

__all__ = [
    # Version
    "__version__",
    # Models
    "TranslationUnit",
    "AgentResult",
    "GateDecision",
    "Verdict",
    "WorkflowState",
    "TranslationRecord",
    # Utils
    "get_bedrock_client",
    "get_config",
    "get_thresholds",
    # Prompts
    "load_prompt",
    "get_template_loader",
]
