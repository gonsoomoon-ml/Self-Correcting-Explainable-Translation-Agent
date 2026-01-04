"""
가격 계산 유틸리티

토큰 사용량 기반 비용 계산.
config/pricing.json에서 가격 정보 로드.
"""

import json
import os
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class CostBreakdown:
    """비용 상세 내역"""
    input_cost: float
    output_cost: float
    cache_read_cost: float
    cache_write_cost: float
    total_cost: float

    def to_dict(self) -> Dict:
        return {
            "input_cost": round(self.input_cost, 6),
            "output_cost": round(self.output_cost, 6),
            "cache_read_cost": round(self.cache_read_cost, 6),
            "cache_write_cost": round(self.cache_write_cost, 6),
            "total_cost": round(self.total_cost, 6)
        }


# 싱글톤 가격 데이터
_pricing_data: Optional[Dict] = None


def load_pricing(config_path: Optional[str] = None) -> Dict:
    """
    pricing.json에서 가격 정보 로드

    Args:
        config_path: pricing.json 경로. 기본값은 config/pricing.json

    Returns:
        가격 정보 딕셔너리
    """
    global _pricing_data

    if _pricing_data is not None:
        return _pricing_data

    if config_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(base_dir, "config", "pricing.json")

    with open(config_path, "r", encoding="utf-8") as f:
        _pricing_data = json.load(f)

    return _pricing_data


def get_model_pricing(model_key: str) -> Dict:
    """
    특정 모델의 가격 정보 조회

    Args:
        model_key: 모델 키 (예: "claude-opus-4-5", "claude-sonnet-4-5")

    Returns:
        모델 가격 정보
    """
    pricing = load_pricing()

    if model_key not in pricing["models"]:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(pricing['models'].keys())}")

    return pricing["models"][model_key]


def calculate_cost(
    token_usage: Dict[str, int],
    model_key: str = "claude-sonnet-4-5",
    use_batch: bool = False
) -> CostBreakdown:
    """
    토큰 사용량 기반 비용 계산

    Args:
        token_usage: 토큰 사용량 딕셔너리
            - input: 입력 토큰
            - output: 출력 토큰
            - cache_read: 캐시 읽기 토큰 (선택)
            - cache_write: 캐시 쓰기 토큰 (선택)
        model_key: 모델 키 (기본: "claude-sonnet-4-5")
        use_batch: 배치 가격 적용 여부

    Returns:
        CostBreakdown: 비용 상세 내역

    Example:
        >>> usage = {"input": 4538, "output": 1138, "cache_read": 0, "cache_write": 0}
        >>> cost = calculate_cost(usage, "claude-sonnet-4-5")
        >>> print(f"Total: ${cost.total_cost:.4f}")
    """
    pricing = get_model_pricing(model_key)

    # 토큰 추출
    input_tokens = token_usage.get("input", 0)
    output_tokens = token_usage.get("output", 0)
    cache_read_tokens = token_usage.get("cache_read", 0)
    cache_write_tokens = token_usage.get("cache_write", 0)

    # MTok (백만 토큰) 단위로 변환
    input_mtok = input_tokens / 1_000_000
    output_mtok = output_tokens / 1_000_000
    cache_read_mtok = cache_read_tokens / 1_000_000
    cache_write_mtok = cache_write_tokens / 1_000_000

    # 가격 계산
    if use_batch:
        input_cost = input_mtok * pricing["batch_input"]
        output_cost = output_mtok * pricing["batch_output"]
    else:
        input_cost = input_mtok * pricing["input"]
        output_cost = output_mtok * pricing["output"]

    cache_read_cost = cache_read_mtok * pricing["cache_read"]
    cache_write_cost = cache_write_mtok * pricing["cache_write_5m"]  # 기본 5분 TTL

    total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost

    return CostBreakdown(
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_read_cost,
        cache_write_cost=cache_write_cost,
        total_cost=total_cost
    )


def calculate_workflow_cost(
    token_usage: Dict[str, int],
    model_distribution: Optional[Dict[str, float]] = None
) -> CostBreakdown:
    """
    워크플로우 전체 비용 계산 (여러 모델 사용 시)

    번역 워크플로우는 여러 모델을 사용:
    - translator: Opus 4.5
    - backtranslator: Sonnet 4.5
    - accuracy_evaluator: Sonnet 4.5
    - compliance_evaluator: Sonnet 4.5
    - quality_evaluator: Opus 4.5

    Args:
        token_usage: 총 토큰 사용량
        model_distribution: 모델별 토큰 비율 (기본: 추정치 사용)

    Returns:
        CostBreakdown: 비용 상세 내역
    """
    if model_distribution is None:
        # 기본 분배 추정 (워크플로우 기반)
        # Opus: translator + quality_evaluator (~40%)
        # Sonnet: backtranslator + accuracy + compliance (~60%)
        model_distribution = {
            "claude-opus-4-5": 0.40,
            "claude-sonnet-4-5": 0.60
        }

    total_input = token_usage.get("input", 0)
    total_output = token_usage.get("output", 0)
    total_cache_read = token_usage.get("cache_read", 0)
    total_cache_write = token_usage.get("cache_write", 0)

    total_cost = CostBreakdown(0, 0, 0, 0, 0)

    for model_key, ratio in model_distribution.items():
        model_usage = {
            "input": int(total_input * ratio),
            "output": int(total_output * ratio),
            "cache_read": int(total_cache_read * ratio),
            "cache_write": int(total_cache_write * ratio)
        }

        cost = calculate_cost(model_usage, model_key)

        total_cost.input_cost += cost.input_cost
        total_cost.output_cost += cost.output_cost
        total_cost.cache_read_cost += cost.cache_read_cost
        total_cost.cache_write_cost += cost.cache_write_cost
        total_cost.total_cost += cost.total_cost

    return total_cost


def format_cost(cost: CostBreakdown, include_breakdown: bool = False) -> str:
    """
    비용을 읽기 쉬운 문자열로 포맷

    Args:
        cost: CostBreakdown 객체
        include_breakdown: 상세 내역 포함 여부

    Returns:
        포맷된 비용 문자열
    """
    if include_breakdown:
        return (
            f"Total: ${cost.total_cost:.6f}\n"
            f"  Input:       ${cost.input_cost:.6f}\n"
            f"  Output:      ${cost.output_cost:.6f}\n"
            f"  Cache Read:  ${cost.cache_read_cost:.6f}\n"
            f"  Cache Write: ${cost.cache_write_cost:.6f}"
        )
    else:
        return f"${cost.total_cost:.6f}"
