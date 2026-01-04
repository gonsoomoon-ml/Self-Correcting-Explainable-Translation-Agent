"""
도구 결과 모델 - 번역 및 역번역 도구의 반환 타입

도구(tool) 함수에서 반환하는 결과 데이터 구조를 정의합니다.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TranslationResult:
    """번역 결과"""
    translation: str                              # 메인 번역
    candidates: List[str] = field(default_factory=list)  # 모든 번역 후보
    notes: Optional[str] = None                   # 번역 노트
    token_usage: Optional[Dict[str, int]] = None  # 토큰 사용량
    latency_ms: int = 0                           # 응답 시간 (밀리초)


@dataclass
class BacktranslationResult:
    """역번역 결과"""
    backtranslation: str                          # 역번역 텍스트
    notes: Optional[str] = None                   # 역번역 노트 (의미 관찰)
    token_usage: Optional[Dict[str, int]] = None  # 토큰 사용량
    latency_ms: int = 0                           # 응답 시간 (밀리초)
