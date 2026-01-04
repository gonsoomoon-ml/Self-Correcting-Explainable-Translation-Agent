#!/bin/bash

# =============================================================================
# Translation Agent 환경 설정 스크립트 (필수)
# =============================================================================
# 사용법:
#   ./setup/create_env.sh
#
# 이 스크립트는 프로젝트 실행 전 반드시 실행해야 합니다.
# 기본 패키지 + OTEL Observability 패키지를 모두 설치합니다.
# =============================================================================

set -e

echo ""
echo "========================================"
echo " Translation Agent - Environment Setup"
echo "========================================"
echo ""

# 프로젝트 루트로 이동
cd "$(dirname "$0")/.."
PROJECT_ROOT=$(pwd)
echo "Project root: $PROJECT_ROOT"
echo ""

# Step 1: 의존성 설치
echo "[1/2] Installing dependencies..."
uv sync --quiet
echo "      ✓ All packages installed"

# Step 2: 설치 확인
echo "[2/2] Verifying installation..."
STRANDS_VER=$(uv run --no-sync python -c "import strands; print('installed')" 2>/dev/null || echo "NOT FOUND")
echo "      strands-agents: $STRANDS_VER"

echo ""
echo "========================================"
echo " ✓ Setup Complete!"
echo "========================================"
echo ""
echo "다음 단계:"
echo ""
echo "  1. AWS 인증 설정:"
echo "     aws configure"
echo ""
echo "  2. 번역 워크플로우 실행:"
echo "     cd 01_explainable_translate_agent"
echo "     uv run python test_workflow.py"
echo ""
echo "  3. CloudWatch에서 트레이스 확인:"
echo "     https://console.aws.amazon.com/cloudwatch/home#gen-ai-observability"
echo ""