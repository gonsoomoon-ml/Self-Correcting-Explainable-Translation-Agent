"""
결과 포맷터 - 워크플로우 결과를 JSON 직렬화 가능한 dict로 변환

test_workflow.py 및 다른 스크립트에서 재사용 가능.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from src.models.workflow_state import WorkflowState
from src.utils.pricing import calculate_workflow_cost


def format_workflow_result(result: dict) -> dict:
    """
    워크플로우 결과를 JSON 직렬화 가능한 dict로 변환.

    구조:
        - 상단: summary (key, translation, scores, verdict 등)
        - 하단: details (evaluations, metrics 등)

    Args:
        result: TranslationWorkflowGraph.run() 반환값

    Returns:
        JSON 직렬화 가능한 dict
    """
    state_value = result["workflow_state"].value

    # === SUMMARY (상단) ===
    output = {
        "key": result["unit"].key,
        "source_text": result["unit"].source_text,
        "translation": None,
        "workflow_state": state_value,
        "attempt_count": result.get("attempt_count", 1),
        "scores": {},
        "verdict": None,
        "can_publish": False,
        "total_latency_ms": 0,
        "created_at": datetime.now().isoformat(),
    }

    # 번역 결과 (summary)
    if "translation_result" in result:
        output["translation"] = result["translation_result"].translation

    # 게이트 판정 (summary)
    if "gate_decision" in result:
        gd = result["gate_decision"]
        output["scores"] = gd.scores
        output["verdict"] = gd.verdict.value
        output["can_publish"] = gd.can_publish
        output["total_latency_ms"] = gd.total_latency_ms

    # === DETAILS (하단) ===
    details = {
        "source_lang": result["unit"].source_lang,
        "target_lang": result["unit"].target_lang,
        "glossary": result["unit"].glossary,
    }

    # 번역 상세
    if "translation_result" in result:
        tr = result["translation_result"]
        details["translation"] = {
            "candidates": tr.candidates,
            "notes": tr.notes,
            "latency_ms": tr.latency_ms
        }

    # 역번역 상세
    if "backtranslation_result" in result:
        bt = result["backtranslation_result"]
        details["backtranslation"] = {
            "text": bt.backtranslation,
            "notes": bt.notes,
            "latency_ms": bt.latency_ms
        }

    # 평가 상세
    if "agent_results" in result:
        details["evaluations"] = []
        for ar in result["agent_results"]:
            eval_dict = {
                "agent": ar.agent_name,
                "score": ar.score,
                "verdict": ar.verdict,
                "issues": ar.issues,
                "reasoning_chain": ar.reasoning_chain,
                "corrections": [
                    {"original": c.original, "suggested": c.suggested, "reason": c.reason}
                    for c in ar.corrections
                ],
                "latency_ms": ar.latency_ms
            }
            details["evaluations"].append(eval_dict)

    # 게이트 판정 상세
    if "gate_decision" in result:
        gd = result["gate_decision"]
        details["gate_decision"] = {
            "verdict": gd.verdict.value,
            "can_publish": gd.can_publish,
            "scores": gd.scores,
            "min_score": gd.min_score,
            "avg_score": gd.avg_score,
            "message": gd.message,
            "blocker_agent": gd.blocker_agent,
            "review_agents": gd.review_agents,
            "agent_agreement_score": gd.agent_agreement_score,
            "total_latency_ms": gd.total_latency_ms
        }

    # 시도 히스토리 (디버깅용 상세 정보 포함)
    if "attempt_history" in result:
        details["attempt_history"] = [
            {
                "attempt": h["attempt"],
                "verdict": h["verdict"],
                "scores": h["scores"],
                "message": h["message"],
                "issues": h.get("issues", {}),
                "corrections": h.get("corrections", {}),
            }
            for h in result["attempt_history"]
        ]

    # 메트릭 상세
    if "metrics" in result:
        m = result["metrics"]

        # 비용 계산
        cost = calculate_workflow_cost(m.token_usage)

        details["metrics"] = {
            "total_latency_ms": m.total_latency_ms,
            "translation_latency_ms": m.translation_latency_ms,
            "backtranslation_latency_ms": m.backtranslation_latency_ms,
            "evaluation_latency_ms": m.evaluation_latency_ms,
            "attempt_count": m.attempt_count,
            "token_usage": m.token_usage,
            "cost_usd": cost.to_dict()
        }

        # summary에도 비용 추가
        output["cost_usd"] = round(cost.total_cost, 6)

    # 오류
    if "error" in result:
        details["error"] = result["error"]

    output["details"] = details

    return output


def calculate_batch_stats(results: List[dict]) -> dict:
    """배치 결과 통계 계산"""
    total = len(results)
    return {
        "total": total,
        "published": sum(1 for r in results if r.get("workflow_state") == WorkflowState.PUBLISHED),
        "rejected": sum(1 for r in results if r.get("workflow_state") == WorkflowState.REJECTED),
        "pending": sum(1 for r in results if r.get("workflow_state") == WorkflowState.PENDING_REVIEW),
        "failed": sum(1 for r in results if r.get("workflow_state") == WorkflowState.FAILED),
        "regenerating": sum(1 for r in results if r.get("workflow_state") == WorkflowState.REGENERATING),
    }


def save_batch_summary(results: List[dict], run_dir: Path) -> Path:
    """배치 결과 요약을 JSON 파일로 저장"""
    stats = calculate_batch_stats(results)

    # 평균 점수 계산
    all_scores = []
    for r in results:
        if "gate_decision" in r:
            all_scores.append(r["gate_decision"].avg_score)
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

    # 총 지연시간 및 토큰
    total_latency = 0
    total_tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    for r in results:
        if "metrics" in r:
            total_latency += r["metrics"].total_latency_ms
            for key in total_tokens:
                total_tokens[key] += r["metrics"].token_usage.get(key, 0)

    # 총 비용 계산
    total_cost = calculate_workflow_cost(total_tokens)

    summary = {
        "run_id": run_dir.name,
        "created_at": datetime.now().isoformat(),
        "total": stats["total"],
        "published": stats["published"],
        "rejected": stats["rejected"],
        "pending_review": stats["pending"],
        "regenerating": stats["regenerating"],
        "failed": stats["failed"],
        "success_rate": round(stats["published"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0,
        "avg_score": round(avg_score, 2),
        "total_latency_ms": total_latency,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost.total_cost, 6),
        "cost_per_item_usd": round(total_cost.total_cost / stats["total"], 6) if stats["total"] > 0 else 0,
        "items": [r["unit"].key for r in results]
    }

    file_path = run_dir / "_summary.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return file_path
