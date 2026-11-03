#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data/local"
echo "JobLens Agent workspace ready: $ROOT"
echo "首次安装依赖：(cd services/backend && uv sync) && (cd apps/web && pnpm install --frozen-lockfile)"
echo "隔离合成演示：python3 scripts/demo.py（不读取真实库，不调用模型）"
