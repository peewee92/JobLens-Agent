#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data/local"
echo "JobLens Agent workspace ready: $ROOT"
echo "Next: implement Roadmap Phase 1 in services/api."
