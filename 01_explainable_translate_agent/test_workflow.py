#!/usr/bin/env python3
"""
워크플로우 테스트 스크립트

번역 파이프라인의 전체 흐름을 테스트합니다.

사전 준비:
    ./setup/create_env.sh  # 필수 (최초 1회)

사용법:
    uv run python test_workflow.py                              # 단일 테스트
    uv run python test_workflow.py --input examples/single/ui.json
    uv run python test_workflow.py --batch --input examples/batch/mixed.json

옵션:
    --input FILE        입력 JSON 파일 (기본: examples/single/default.json)
    --batch             배치 모드 (모든 테스트 항목 실행)
    --max-regen N       최대 재생성 횟수 (기본: 1)
    --session-id ID     OTEL 세션 ID 지정
"""

# =============================================================================
# 의존성
# =============================================================================
import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

from src.models import TranslationUnit
from src.graph import TranslationWorkflowGraph, WorkflowConfig
from src.utils.pricing import calculate_workflow_cost
from src.utils.result_formatter import (
    format_workflow_result,
    calculate_batch_stats,
    save_batch_summary,
)

# =============================================================================
# OTEL 설정 (선택적)
# - 설치됨: CloudWatch로 트레이스 전송
# - 미설치: 더미 세션으로 대체 (기능 정상 작동)
# =============================================================================
try:
    from src.utils.strands_utils import observability_session
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    from contextlib import contextmanager
    @contextmanager
    def observability_session(**kwargs):
        yield {"session_id": kwargs.get("session_id") or "no-otel"}

# =============================================================================
# 설정
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 불필요한 로그 억제
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("src.utils.strands_utils").setLevel(logging.WARNING)
logging.getLogger("strands.telemetry.metrics").setLevel(logging.WARNING)

RESULTS_DIR = Path(__file__).parent / "results"    # 결과 저장 위치
EXAMPLES_DIR = Path(__file__).parent / "examples"  # 예제 입력 파일


# =============================================================================
# 유틸리티 함수
# =============================================================================
def log_header(*lines: str) -> None:
    """구분선으로 감싼 헤더 출력"""
    logger.info(f"\n{'='*60}")
    for line in lines:
        logger.info(line)
    logger.info("="*60)


def log_section(title: str) -> None:
    """섹션 제목 출력"""
    logger.info(f"\n--- {title} ---")


def print_json_block(title: str, data: dict, summary_only: bool = False) -> None:
    """JSON 블록 출력 (summary_only=True면 details 제외)"""
    print(f"\n{'='*60}")
    print(title)
    print("="*60)
    if summary_only and "details" in data:
        summary = {k: v for k, v in data.items() if k != "details"}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def load_test_units(json_path: Path = None) -> List[TranslationUnit]:
    """JSON 파일에서 테스트 데이터 로드"""
    if json_path is None:
        json_path = EXAMPLES_DIR / "single" / "default.json"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return [TranslationUnit(**item) for item in data]


# =============================================================================
# 테스트 데이터
# - config/test_data.yaml 에서 로드 (기본값)
# - --input 옵션으로 다른 파일 지정 가능
# - 각 항목: key, source_text, source_lang, target_lang, glossary 등
# =============================================================================


def get_timestamp() -> str:
    """타임스탬프 생성 (yyyy-mm-dd-hh-mm-ss-mms)"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S") + f"-{now.microsecond // 1000:03d}"


def save_result(result: dict, run_dir: Path) -> Path:
    """단일 결과를 JSON 파일로 저장"""
    key = result["unit"].key
    file_path = run_dir / f"{key}.json"

    output = format_workflow_result(result)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return file_path


def log_batch_stats(stats: dict) -> None:
    """배치 통계를 로그로 출력"""
    log_section("배치 결과")
    logger.info(f"  발행: {stats['published']}/{stats['total']}")
    logger.info(f"  거부: {stats['rejected']}/{stats['total']}")
    logger.info(f"  검수대기: {stats['pending']}/{stats['total']}")
    logger.info(f"  실패: {stats['failed']}/{stats['total']}")


def log_single_result(result: dict) -> None:
    """단일 번역 결과를 트리 형태로 출력"""
    m = result.get('metrics')
    total_ms = m.total_latency_ms if m else 0
    attempt = result.get('attempt_count', 1)
    state = result['workflow_state'].value

    # 상태 아이콘
    icon = {"published": "✅", "pending_review": "⚠️", "rejected": "❌", "failed": "💥"}.get(state, "🔄")

    # 헤더
    print(f"\n{icon} 워크플로우 완료 ({total_ms/1000:.1f}s)")

    # 번역
    if 'translation_result' in result:
        tr = result['translation_result']
        print(f"├─ 번역: {tr.latency_ms}ms")
        print(f"│   └─ {tr.translation[:60]}{'...' if len(tr.translation) > 60 else ''}")

    # 역번역
    if 'backtranslation_result' in result:
        bt = result['backtranslation_result']
        print(f"├─ 역번역: {bt.latency_ms}ms")
        print(f"│   └─ {bt.backtranslation[:60]}{'...' if len(bt.backtranslation) > 60 else ''}")

    # 평가
    if 'agent_results' in result:
        eval_latency = m.evaluation_latency_ms if m else 0
        print(f"├─ 평가: {eval_latency}ms")
        agents = result['agent_results']
        for i, ar in enumerate(agents):
            is_last = (i == len(agents) - 1)
            prefix = "│   └─" if is_last else "│   ├─"
            score_icon = "✓" if ar.score >= 4 else ("△" if ar.score == 3 else "✗")
            print(f"{prefix} {ar.agent_name}: {ar.score} {score_icon}")
            # 이슈가 있으면 표시
            if ar.issues and ar.score < 4:
                issue_prefix = "│       └─" if is_last else "│   │   └─"
                print(f"{issue_prefix} {ar.issues[0][:50]}...")

    # 판정 (시도 히스토리 포함)
    if 'attempt_history' in result and len(result['attempt_history']) > 1:
        print(f"└─ 판정 ({attempt}회 시도)")
        history = result['attempt_history']
        for i, h in enumerate(history):
            is_last = (i == len(history) - 1)
            prefix = "    └─" if is_last else "    ├─"
            scores_str = ", ".join(f"{k}:{v}" for k, v in h['scores'].items())
            print(f"{prefix} [시도 {h['attempt']}] {h['verdict']} ({scores_str})")
            if h['message'] and is_last:
                print(f"        └─ {h['message']}")
    elif 'gate_decision' in result:
        gd = result['gate_decision']
        print(f"└─ 판정: {gd.verdict.value}")
        if gd.message:
            print(f"    └─ {gd.message}")

    # 비용
    if m:
        cost = calculate_workflow_cost(m.token_usage)
        print(f"\n💰 비용: ${cost.total_cost:.4f} | 토큰: {m.token_usage['input']:,}+{m.token_usage['output']:,}")

    # 오류
    if 'error' in result:
        print(f"\n❌ 오류: {result['error']}")


# =============================================================================
# 테스트 함수
# =============================================================================
async def test_single_translation(unit: TranslationUnit, config: WorkflowConfig) -> dict:
    """단일 번역 테스트"""
    log_header(
        f"테스트: {unit.key}",
        f"원문: {unit.source_text[:50]}...",
        f"대상 언어: {unit.target_lang}"
    )

    graph = TranslationWorkflowGraph(config)
    result = await graph.run(unit)

    log_single_result(result)

    # 결과 저장
    timestamp = get_timestamp()
    run_dir = RESULTS_DIR / "single" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_result(result, run_dir)
    logger.info(f"\n📁 결과 저장: {file_path}")

    # JSON 출력 (요약만)
    output_dict = format_workflow_result(result)
    print_json_block("📄 Result JSON:", output_dict, summary_only=True)

    return result


async def test_batch_translation(units: list, config: WorkflowConfig, concurrency: int = 2) -> list:
    """배치 번역 테스트"""
    log_header(f"배치 테스트: {len(units)}개 항목, 동시성 {concurrency}")

    graph = TranslationWorkflowGraph(config)
    results = await graph.run_batch(units, concurrency=concurrency)

    # 통계
    stats = calculate_batch_stats(results)
    log_batch_stats(stats)

    # 결과 저장
    timestamp = get_timestamp()
    run_dir = RESULTS_DIR / "batch" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        save_result(result, run_dir)

    summary_path = save_batch_summary(results, run_dir)
    logger.info(f"\n📁 결과 저장: {run_dir}")
    logger.info(f"📊 요약: {summary_path}")

    # 각 결과 JSON 출력 (요약만)
    for result in results:
        output_dict = format_workflow_result(result)
        print_json_block(f"📄 Result JSON ({result['unit'].key}):", output_dict, summary_only=True)

    # 요약 JSON 출력
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    print_json_block("📊 Summary JSON:", summary)

    return results


# =============================================================================
# 메인 진입점
# =============================================================================
async def main():
    """명령줄 인자를 파싱하고 적절한 테스트 모드 실행"""
    parser = argparse.ArgumentParser(description="번역 워크플로우 테스트")
    parser.add_argument("--input", type=str, help="입력 YAML 파일 경로")
    parser.add_argument("--batch", action="store_true", help="배치 테스트 실행")
    parser.add_argument("--max-regen", type=int, default=1, help="최대 재생성 횟수 (기본: 1)")
    parser.add_argument("--session-id", type=str, help="커스텀 세션 ID")
    parser.add_argument("--debug", action="store_true", help="DEBUG 로그 레벨 활성화 (프롬프트 출력)")
    args = parser.parse_args()

    # DEBUG 모드 설정
    if args.debug:
        logging.getLogger("src.tools").setLevel(logging.DEBUG)
        # strands 내부 로그는 숨김
        logging.getLogger("strands").setLevel(logging.WARNING)

    # 테스트 데이터 로드
    input_path = Path(args.input) if args.input else None
    test_units = load_test_units(input_path)

    logger.info(f"OTEL: {'ENABLED' if OTEL_AVAILABLE else 'DISABLED'}")

    # 워크플로우 설정
    config = WorkflowConfig(
        max_regenerations=args.max_regen,
        num_candidates=1,
        enable_backtranslation=True,
        timeout_seconds=120
    )

    # Observability 세션으로 실행
    workflow_name = "batch" if args.batch else "single"

    with observability_session(
        session_id=args.session_id,
        workflow_name=f"translation-{workflow_name}",
        metadata={"test_mode": workflow_name}
    ) as session:
        logger.info(f"Session ID: {session['session_id']}")

        if args.batch:
            await test_batch_translation(test_units, config)
        else:
            await test_single_translation(test_units[0], config)

    if OTEL_AVAILABLE:
        logger.info("View traces: https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability")


if __name__ == "__main__":
    asyncio.run(main())
