"""
SOPs (Standard Operating Procedures) - 의사결정 로직 레이어

번역 파이프라인의 의사결정 로직을 담당하는 모듈:

- EvaluationGateSOP: 에이전트 점수 기반 Pass/Fail/Regenerate 판정
- RegenerationSOP: 번역 재시도를 위한 Maker-Checker 피드백 수집
"""

from sops.evaluation_gate import (
    EvaluationGateSOP,
    EvaluationGateConfig,
)
from sops.regeneration import (
    RegenerationSOP,
    RegenerationFeedback,
)

__all__ = [
    # 평가 게이트
    "EvaluationGateSOP",
    "EvaluationGateConfig",
    # 재생성
    "RegenerationSOP",
    "RegenerationFeedback",
]
