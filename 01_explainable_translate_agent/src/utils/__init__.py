"""
Utility modules for the translation agent
"""

# Strands Agent utilities (recommended)
from .strands_utils import (
    # Configuration
    ModelConfig as StrandsModelConfig,
    StrandsConfig,
    load_config as load_strands_config,
    get_config as get_strands_config,
    # Model & Agent Creation
    get_model,
    get_agent,
    create_system_prompt_with_cache,
    # State Management
    get_agent_state,
    get_agent_state_all,
    update_agent_state,
    update_agent_state_all,
    # Execution
    extract_usage_from_agent,
    run_agent_async,
    run_agent_sync,
    parse_response_text,
    # Token Tracking
    TokenTracker,
)

# Observability (OpenTelemetry-based, aligned with AgentCore patterns)
from .observability import (
    # Constants
    Colors,
    MODEL_PRICING,
    # Session Context (Baggage)
    set_session_context,
    get_session_id,
    # Tracer
    get_tracer,
    # Span Helpers
    add_span_event,
    set_span_attribute,
    set_span_status,
    record_exception,
    # Context Managers
    trace_agent,
    trace_workflow,
    # Node Logging
    log_node_start,
    log_node_complete,
    # Cost
    calculate_cost,
)

# Config loader
from .config import (
    ConfigLoader,
    get_config_loader,
    get_config,
    get_thresholds,
    get_risk_profile,
)

# Deprecated: raw boto3 client (use strands_utils instead)
from .bedrock_client import (
    BedrockClient,
    ModelConfig,
    get_bedrock_client,
    create_bedrock_client,
)

__all__ = [
    # Strands Agent utilities (recommended)
    "StrandsModelConfig",
    "StrandsConfig",
    "load_strands_config",
    "get_strands_config",
    "get_model",
    "get_agent",
    "create_system_prompt_with_cache",
    # State Management
    "get_agent_state",
    "get_agent_state_all",
    "update_agent_state",
    "update_agent_state_all",
    # Execution
    "extract_usage_from_agent",
    "run_agent_async",
    "run_agent_sync",
    "parse_response_text",
    # Token Tracking
    "TokenTracker",
    # Observability (OpenTelemetry-based)
    "Colors",
    "MODEL_PRICING",
    "set_session_context",
    "get_session_id",
    "get_tracer",
    "add_span_event",
    "set_span_attribute",
    "set_span_status",
    "record_exception",
    "trace_agent",
    "trace_workflow",
    "log_node_start",
    "log_node_complete",
    "calculate_cost",
    # Config loader
    "ConfigLoader",
    "get_config_loader",
    "get_config",
    "get_thresholds",
    "get_risk_profile",
    # Deprecated
    "BedrockClient",
    "ModelConfig",
    "get_bedrock_client",
    "create_bedrock_client",
]
