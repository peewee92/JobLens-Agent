#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 - <<'PY' "$ROOT"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
for p in (root / 'packages/contracts/schemas').glob('*.json'):
    json.loads(p.read_text())
    print('valid json:', p.relative_to(root))
json.loads((root / 'data/samples/collector-report-minimal.json').read_text())
print('valid json: data/samples/collector-report-minimal.json')
PY

for file in "$ROOT"/apps/collector-extension/*.js "$ROOT"/apps/collector-extension/tests/*.js; do
  node --check "$file" >/dev/null
  echo "syntax ok: ${file#$ROOT/}"
done

echo "verify passed"
