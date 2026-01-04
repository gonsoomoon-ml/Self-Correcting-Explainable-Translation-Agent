"""
평가 게이트 SOP - Pass/Fail/Regenerate/Escalate 판정

목적: 3개 평가 에이전트의 결과를 기반으로 최종 판정 결정

비즈니스 규칙:
- 모든 에이전트 점수 = 5: 자동 통과 (발행 가능)
- 어떤 에이전트라도 점수 <= 2: 차단 (즉시 거부)
- 어떤 에이전트라도 점수 = 3 또는 4:
  - 첫 번째 시도: 재생성 (피드백으로 재시도)
  - 최대 재시도 후: 에스컬레이션 (PM 검수)
- 에이전트 간 점수 차이 >= 3: 에스컬레이션 (불일치 평가)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

from src.models.agent_result import AgentResult
from src.models.gate_decision import GateDecision, Verdict


@dataclass
class EvaluationGateConfig:
    """평가 게이트 임계값 설정"""
    pass_threshold: int = 5       # 통과 최소 점수 (모든 에이전트 5점 필요)
    fail_threshold: int = 2       # 차단 최대 점수
    max_regenerations: int = 1    # 최대 재시도 횟수
    disagreement_threshold: int = 3  # 에스컬레이션 전 최대 점수 차이


class EvaluationGateSOP:
    """
    평가 게이트 SOP - Release Guard

    번역의 발행 가능 여부, 재생성 필요 여부, 인간 검수 필요 여부를
    결정하는 의사결정 로직을 구현합니다.
    """

    def __init__(self, config: Optional[EvaluationGateConfig] = None):
        """
        선택적 사용자 정의 설정으로 초기화.

        Args:
            config: 사용자 정의 임계값 설정. 미제공시 기본값 사용.
        """
        self.config = config or EvaluationGateConfig()

    def decide(
        self,
        agent_results: List[AgentResult],
        attempt_count: int = 1,
        start_time: Optional[datetime] = None
    ) -> GateDecision:
        """
        평가 결과를 기반으로 최종 판정 결정.

        Args:
            agent_results: 3개 에이전트 평가 결과 리스트 (accuracy, compliance, quality)
            attempt_count: 현재 시도 횟수 (1부터 시작, 재생성시 증가)
            start_time: 지연시간 계산을 위한 평가 시작 시간

        Returns:
            GateDecision: 모든 지원 정보가 포함된 최종 판정

        Raises:
            ValueError: agent_results가 비어있거나 잘못된 데이터 포함시
        """
        if not agent_results:
            raise ValueError("최소 하나의 에이전트 결과가 필요합니다")

        # 점수 추출
        scores = {r.agent_name: r.score for r in agent_results}
        min_score = min(scores.values())
        max_score = max(scores.values())
        avg_score = sum(scores.values()) / len(scores)

        # 에이전트 일치도 계산 (0-1 스케일, 1 = 완벽 일치)
        disagreement = max_score - min_score
        agreement_score = 1.0 - (disagreement / 5.0)

        # 모든 에이전트의 Chain-of-Thought 수집
        reasoning_chains = {
            r.agent_name: r.reasoning_chain
            for r in agent_results
        }

        # 모든 에이전트의 수정 제안 집계
        all_corrections = []
        for r in agent_results:
            all_corrections.extend([c.model_dump() for c in r.corrections])

        # 총 지연시간 계산
        total_latency = sum(r.latency_ms for r in agent_results)

        # 기본 판정 kwargs 구성
        base_kwargs = {
            "scores": scores,
            "min_score": min_score,
            "avg_score": round(avg_score, 2),
            "reasoning_chains": reasoning_chains,
            "corrections": all_corrections,
            "agent_agreement_score": round(agreement_score, 2),
            "total_latency_ms": total_latency
        }

        # Case 1: 모든 에이전트 통과 (점수 >= 4)
        if all(s >= self.config.pass_threshold for s in scores.values()):
            return GateDecision(
                verdict=Verdict.PASS,
                can_publish=True,
                message=self._build_pass_message(scores),
                **base_kwargs
            )

        # Case 2: 치명적 실패 (어떤 점수라도 <= 2)
        blocking_results = [
            r for r in agent_results
            if r.score <= self.config.fail_threshold
        ]
        if blocking_results:
            blocker = blocking_results[0]
            return GateDecision(
                verdict=Verdict.BLOCK,
                can_publish=False,
                blocker_agent=blocker.agent_name,
                message=self._build_block_message(blocker),
                **base_kwargs
            )

        # Case 3: 심각한 에이전트 불일치
        if disagreement >= self.config.disagreement_threshold:
            return GateDecision(
                verdict=Verdict.ESCALATE,
                can_publish=False,
                review_agents=list(scores.keys()),
                message=self._build_disagreement_message(scores, disagreement),
                **base_kwargs
            )

        # Case 4: 경계 점수 (점수 < pass_threshold) - Maker-Checker Loop
        borderline_agents = [
            name for name, score in scores.items()
            if score < self.config.pass_threshold and score > self.config.fail_threshold
        ]

        # 시도 횟수가 남아있으면 재생성 시도
        if attempt_count <= self.config.max_regenerations:
            return GateDecision(
                verdict=Verdict.REGENERATE,
                can_publish=False,
                review_agents=borderline_agents,
                message=self._build_regenerate_message(borderline_agents, attempt_count),
                **base_kwargs
            )

        # Case 5: 최대 재생성 횟수 소진 -> PM 에스컬레이션
        return GateDecision(
            verdict=Verdict.ESCALATE,
            can_publish=False,
            review_agents=borderline_agents,
            message=self._build_escalate_message(borderline_agents, attempt_count),
            **base_kwargs
        )

    def _build_pass_message(self, scores: Dict[str, int]) -> str:
        """사람이 읽을 수 있는 통과 메시지 생성"""
        score_str = ", ".join(f"{k}={v}" for k, v in scores.items())
        return f"모든 에이전트 통과 [{score_str}]. 발행 준비 완료."

    def _build_block_message(self, blocker: AgentResult) -> str:
        """사람이 읽을 수 있는 차단 메시지 생성"""
        issues_str = "; ".join(blocker.issues) if blocker.issues else "치명적 품질 문제"
        return f"{blocker.agent_name}에 의해 차단됨 (점수={blocker.score}): {issues_str}"

    def _build_disagreement_message(
        self,
        scores: Dict[str, int],
        disagreement: int
    ) -> str:
        """에이전트 불일치 케이스 메시지 생성"""
        score_str = ", ".join(f"{k}={v}" for k, v in scores.items())
        return f"에이전트 불일치 ({disagreement}점 차이): [{score_str}]. PM 검수 필요."

    def _build_regenerate_message(
        self,
        borderline_agents: List[str],
        attempt_count: int
    ) -> str:
        """재생성 케이스 메시지 생성"""
        agents_str = ", ".join(borderline_agents)
        return f"재생성 중 (시도 {attempt_count}/{self.config.max_regenerations}). 문제 에이전트: {agents_str}"

    def _build_escalate_message(
        self,
        borderline_agents: List[str],
        attempt_count: int
    ) -> str:
        """에스컬레이션 케이스 메시지 생성"""
        agents_str = ", ".join(borderline_agents)
        return f"PM 검수 필요. {attempt_count}회 시도 소진. 검수 대상: {agents_str}"

    def get_summary(self, decision: GateDecision) -> Dict:
        """
        로깅/리포팅용 판정 요약 생성.

        Args:
            decision: 요약할 게이트 판정

        Returns:
            로깅에 적합한 요약 정보 Dict
        """
        return {
            "verdict": decision.verdict.value,
            "can_publish": decision.can_publish,
            "scores": decision.scores,
            "min_score": decision.min_score,
            "avg_score": decision.avg_score,
            "agreement": decision.agent_agreement_score,
            "blocker": decision.blocker_agent,
            "review_needed": decision.review_agents,
            "correction_count": len(decision.corrections),
            "latency_ms": decision.total_latency_ms,
            "message": decision.message
        }
