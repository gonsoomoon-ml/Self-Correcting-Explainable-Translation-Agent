"""
Bedrock Client - AWS Bedrock runtime client with retry logic

⚠️ DEPRECATED: This module uses raw boto3 Converse API.
Use strands_utils.py instead for Strands Agent integration with prompt caching.

Migration:
    # Old (deprecated)
    from src.utils.bedrock_client import get_bedrock_client
    client = get_bedrock_client()
    response = client.converse(role="translator", messages=[...])

    # New (recommended)
    from src.utils.strands_utils import get_agent
    agent = get_agent(role="translator", system_prompt="...")
    result = agent("Translate: 안녕하세요")
"""

import boto3
import time
import yaml
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for a specific model role"""
    model_id: str
    max_tokens: int
    temperature: float
    description: str


class BedrockClient:
    """
    AWS Bedrock runtime client with retry logic and configuration.

    Usage:
        client = BedrockClient()
        response = client.converse(
            role="translator",
            messages=[{"role": "user", "content": [{"text": "..."}]}]
        )
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        region_name: Optional[str] = None
    ):
        """
        Initialize Bedrock client.

        Args:
            config_path: Path to models.yaml config file
            region_name: AWS region (overrides config if provided)
        """
        self._load_config(config_path)

        # Override region if provided
        if region_name:
            self.region = region_name

        # Initialize boto3 client
        try:
            self.client = boto3.client(
                service_name="bedrock-runtime",
                region_name=self.region
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Bedrock client: {e}")

    def _load_config(self, config_path: Optional[str] = None):
        """Load configuration from YAML file"""
        if config_path is None:
            # Default to config/models.yaml relative to this file
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            config_path = os.path.join(base_dir, "config", "models.yaml")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            # Use defaults if config not found
            config = self._default_config()

        # Parse configuration
        self.region = config.get("region", "us-west-2")
        self.models: Dict[str, ModelConfig] = {}

        for role, model_cfg in config.get("models", {}).items():
            self.models[role] = ModelConfig(
                model_id=model_cfg["model_id"],
                max_tokens=model_cfg.get("max_tokens", 1500),
                temperature=model_cfg.get("temperature", 0.1),
                description=model_cfg.get("description", "")
            )

        # Retry configuration
        retry_cfg = config.get("retry", {})
        self.max_retries = retry_cfg.get("max_attempts", 3)
        self.base_delay = retry_cfg.get("base_delay_seconds", 1)
        self.max_delay = retry_cfg.get("max_delay_seconds", 10)
        self.exponential_base = retry_cfg.get("exponential_base", 2)

        # Token limits
        token_cfg = config.get("token_limits", {})
        self.max_input_tokens = token_cfg.get("max_input_tokens", 100000)
        self.max_output_tokens = token_cfg.get("max_output_tokens", 4096)

    def _default_config(self) -> dict:
        """Return default configuration"""
        return {
            "region": "us-west-2",
            "models": {
                "translator": {
                    "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                "backtranslator": {
                    "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                    "max_tokens": 1000,
                    "temperature": 0.1
                },
                "accuracy_evaluator": {
                    "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "max_tokens": 1500,
                    "temperature": 0.1
                },
                "compliance_evaluator": {
                    "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "max_tokens": 1500,
                    "temperature": 0.1
                },
                "quality_evaluator": {
                    "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "max_tokens": 1500,
                    "temperature": 0.1
                }
            },
            "retry": {
                "max_attempts": 3,
                "base_delay_seconds": 1,
                "max_delay_seconds": 10,
                "exponential_base": 2
            }
        }

    def get_model_config(self, role: str) -> ModelConfig:
        """Get model configuration for a specific role"""
        if role not in self.models:
            raise ValueError(f"Unknown model role: {role}. Available: {list(self.models.keys())}")
        return self.models[role]

    def converse(
        self,
        role: str,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Call Bedrock Converse API with retry logic.

        Args:
            role: Model role (translator, backtranslator, accuracy_evaluator, etc.)
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt override
            max_tokens: Optional max tokens override
            temperature: Optional temperature override
            stop_sequences: Optional stop sequences

        Returns:
            Bedrock Converse API response

        Raises:
            RuntimeError: If all retries fail
        """
        model_config = self.get_model_config(role)

        # Build request
        request = {
            "modelId": model_config.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens or model_config.max_tokens,
                "temperature": temperature if temperature is not None else model_config.temperature
            }
        }

        # Add system prompt if provided
        if system_prompt:
            request["system"] = [{"text": system_prompt}]

        # Add stop sequences if provided
        if stop_sequences:
            request["inferenceConfig"]["stopSequences"] = stop_sequences

        # Execute with retry
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.converse(**request)
                return response
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Calculate delay with exponential backoff
                    delay = min(
                        self.base_delay * (self.exponential_base ** attempt),
                        self.max_delay
                    )
                    time.sleep(delay)

        raise RuntimeError(
            f"Bedrock API call failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def extract_text(self, response: Dict[str, Any]) -> str:
        """Extract text content from Bedrock response"""
        try:
            return response["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError) as e:
            raise ValueError(f"Failed to extract text from response: {e}")

    def extract_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        """Extract token usage from Bedrock response"""
        usage = response.get("usage", {})
        return {
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0)
        }

    def converse_and_extract(
        self,
        role: str,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Tuple[str, Dict[str, int]]:
        """
        Convenience method to call converse and extract text + usage.

        Returns:
            Tuple of (response_text, token_usage_dict)
        """
        response = self.converse(role, messages, system_prompt, **kwargs)
        text = self.extract_text(response)
        usage = self.extract_usage(response)
        return text, usage


# Singleton instance for convenience
_default_client: Optional[BedrockClient] = None


def get_bedrock_client(config_path: Optional[str] = None) -> BedrockClient:
    """Get or create the default Bedrock client singleton"""
    global _default_client
    if _default_client is None:
        _default_client = BedrockClient(config_path=config_path)
    return _default_client


def create_bedrock_client(
    region_name: str = "us-west-2",
    config_path: Optional[str] = None
) -> BedrockClient:
    """Create a new Bedrock client instance"""
    return BedrockClient(config_path=config_path, region_name=region_name)
