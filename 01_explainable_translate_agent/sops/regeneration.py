"""
재생성 SOP - Maker-Checker 피드백 수집

목적: 번역 재생성을 위해 평가 에이전트로부터 피드백 수집 및 포맷

Maker-Checker 패턴:
- Checker (평가 에이전트): 문제점에 대한 피드백 제공
- Maker (번역 에이전트): 포맷된 피드백 수신
- 이전 문제를 회피한 새로운 번역 생성
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

from src.models.agent_result import AgentResult, Correction


@dataclass
class RegenerationFeedback:
    """
    번역 재생성을 위한 구조화된 피드백.

    실패/경계 평가에서 수집한 모든 문제점과 수정 제안을 포함하여
    번역기가 개선된 번역을 생성하도록 안내합니다.
    """

    # 모든 에이전트에서 집계된 문제점
    previous_issues: List[str] = field(default_factory=list)

    # 에이전트가 제안한 구체적인 수정 사항
    corrections: List[Correction] = field(default_factory=list)

    # 컨텍스트를 위한 에이전트별 추론 과정
    agent_feedbacks: Dict[str, List[str]] = field(default_factory=dict)

    # 재생성을 유발한 에이전트 목록
    triggering_agents: List[str] = field(default_factory=list)

    # 선택적: 참조용 이전 번역
    previous_translation: Optional[str] = None


class RegenerationSOP:
    """
    재생성 SOP - 피드백 수집 및 포맷팅

    Maker-Checker 루프를 구현:
    1. 통과하지 못한 평가 에이전트로부터 피드백 수집
    2. 번역기 프롬프트에 주입할 형태로 피드백 포맷
    3. 번역의 반복적 개선 지원
    """

    # 피드백 수집 임계값 (이보다 낮은 점수의 에이전트가 피드백 제공)
    FEEDBACK_THRESHOLD = 5

    def collect_feedback(
        self,
        agent_results: List[AgentResult],
        previous_translation: Optional[str] = None
    ) -> RegenerationFeedback:
        """
        평가 결과로부터 피드백 수집.

        통과하지 못한 에이전트 (점수 < 5)의 피드백만 수집합니다.
        이들이 수정해야 할 문제를 식별한 에이전트이기 때문입니다.

        Args:
            agent_results: 에이전트 평가 결과 리스트
            previous_translation: 평가된 번역

        Returns:
            RegenerationFeedback: 재생성을 위한 구조화된 피드백
        """
        issues: List[str] = []
        corrections: List[Correction] = []
        agent_feedbacks: Dict[str, List[str]] = {}
        triggering_agents: List[str] = []

        for result in agent_results:
            if result.score < self.FEEDBACK_THRESHOLD:
                # 문제점 수집
                issues.extend(result.issues)

                # 수정 제안 수집
                corrections.extend(result.corrections)

                # 컨텍스트를 위한 추론 과정 수집
                agent_feedbacks[result.agent_name] = result.reasoning_chain

                # 재생성을 유발한 에이전트 추적
                triggering_agents.append(result.agent_name)

        return RegenerationFeedback(
            previous_issues=issues,
            corrections=corrections,
            agent_feedbacks=agent_feedbacks,
            triggering_agents=triggering_agents,
            previous_translation=previous_translation
        )

    def format_feedback_for_prompt(
        self,
        feedback: RegenerationFeedback,
        include_reasoning: bool = True,
        language: str = "ko"
    ) -> str:
        """
        번역기 프롬프트에 주입할 텍스트로 피드백 포맷.

        번역기가 무엇이 잘못되었고 어떻게 개선해야 하는지
        이해할 수 있는 구조화된 피드백 섹션을 생성합니다.

        Args:
            feedback: 평가에서 수집된 피드백
            include_reasoning: 에이전트 추론 과정 포함 여부
            language: 메시지 출력 언어 (ko, en)

        Returns:
            프롬프트 주입용 포맷된 문자열
        """
        if language == "ko":
            return self._format_korean(feedback, include_reasoning)
        return self._format_english(feedback, include_reasoning)

    def _format_korean(
        self,
        feedback: RegenerationFeedback,
        include_reasoning: bool
    ) -> str:
        """한국어로 피드백 포맷"""
        lines = [
            "<previous_feedback>",
            "이전 번역에서 다음 문제가 발견되었습니다:",
            ""
        ]

        # 문제점 나열
        if feedback.previous_issues:
            lines.append("**발견된 문제:**")
            for i, issue in enumerate(feedback.previous_issues, 1):
                lines.append(f"{i}. {issue}")
            lines.append("")

        # 수정 제안 나열
        if feedback.corrections:
            lines.append("**수정 제안:**")
            for correction in feedback.corrections:
                lines.append(f"- '{correction.original}' → '{correction.suggested}'")
                lines.append(f"  사유: {correction.reason}")
            lines.append("")

        # 요청시 에이전트 추론 과정 포함
        if include_reasoning and feedback.agent_feedbacks:
            lines.append("**평가 에이전트 분석:**")
            for agent_name, reasoning in feedback.agent_feedbacks.items():
                lines.append(f"\n[{agent_name}]")
                for step in reasoning:
                    lines.append(f"  - {step}")
            lines.append("")

        # 참조용 이전 번역
        if feedback.previous_translation:
            lines.append("**이전 번역 (참고용):**")
            lines.append(f"```")
            lines.append(feedback.previous_translation)
            lines.append(f"```")
            lines.append("")

        lines.append("위 문제점을 피하여 새로운 번역을 생성하세요.")
        lines.append("</previous_feedback>")

        return "\n".join(lines)

    def _format_english(
        self,
        feedback: RegenerationFeedback,
        include_reasoning: bool
    ) -> str:
        """영어로 피드백 포맷"""
        lines = [
            "<previous_feedback>",
            "The following issues were found in the previous translation:",
            ""
        ]

        # 문제점 나열
        if feedback.previous_issues:
            lines.append("**Issues Found:**")
            for i, issue in enumerate(feedback.previous_issues, 1):
                lines.append(f"{i}. {issue}")
            lines.append("")

        # 수정 제안 나열
        if feedback.corrections:
            lines.append("**Suggested Corrections:**")
            for correction in feedback.corrections:
                lines.append(f"- '{correction.original}' → '{correction.suggested}'")
                lines.append(f"  Reason: {correction.reason}")
            lines.append("")

        # 요청시 에이전트 추론 과정 포함
        if include_reasoning and feedback.agent_feedbacks:
            lines.append("**Agent Analysis:**")
            for agent_name, reasoning in feedback.agent_feedbacks.items():
                lines.append(f"\n[{agent_name}]")
                for step in reasoning:
                    lines.append(f"  - {step}")
            lines.append("")

        # 참조용 이전 번역
        if feedback.previous_translation:
            lines.append("**Previous Translation (for reference):**")
            lines.append(f"```")
            lines.append(feedback.previous_translation)
            lines.append(f"```")
            lines.append("")

        lines.append("Please generate a new translation avoiding the above issues.")
        lines.append("</previous_feedback>")

        return "\n".join(lines)

    def should_regenerate(self, feedback: RegenerationFeedback) -> bool:
        """
        재생성 가치가 있는지 판단.

        개선할 실행 가능한 피드백이 없으면 False 반환.

        Args:
            feedback: 수집된 피드백

        Returns:
            bool: 재생성에 실행 가능한 피드백이 있으면 True
        """
        return bool(feedback.previous_issues or feedback.corrections)

    def get_priority_corrections(
        self,
        feedback: RegenerationFeedback,
        max_corrections: int = 5
    ) -> List[Correction]:
        """
        집중해야 할 가장 중요한 수정 사항 추출.

        핵심 에이전트 순으로 우선순위 부여 (compliance > accuracy > quality).

        Args:
            feedback: 수집된 피드백
            max_corrections: 반환할 최대 수정 사항 수

        Returns:
            우선순위가 지정된 수정 사항 리스트
        """
        # 에이전트 우선순위 순서
        priority_order = ["compliance", "accuracy", "quality"]

        # 에이전트별 수정 사항 그룹화
        agent_corrections: Dict[str, List[Correction]] = {}
        for agent in feedback.triggering_agents:
            agent_corrections[agent] = []

        # 단순화된 버전 - 실제로는 수정 사항에 출처 에이전트 태그 필요
        prioritized = feedback.corrections[:max_corrections]

        return prioritized
