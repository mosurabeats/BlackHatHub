#!/bin/bash
# Build the frontend, run the test suite, and produce a distributable ZIP.
# Usage: scripts/package.sh [--skip-tests]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="1.0.0"
OUT="$ROOT/dist-zip"
NAME="ExecutiveHub-$VERSION"

echo "==> Building frontend"
(cd frontend && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build)

if [ "${1:-}" != "--skip-tests" ]; then
  echo "==> Running tests"
  PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
  (cd backend && "$PY" -m pytest -q)
fi

echo "==> Packaging"
mkdir -p "$OUT"
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/$NAME"
git ls-files -z | tar --null -T - -cf - | tar -xf - -C "$STAGE/$NAME"
# Ship the prebuilt UI so the owner never needs Node.js.
mkdir -p "$STAGE/$NAME/frontend/dist" && cp -R frontend/dist/. "$STAGE/$NAME/frontend/dist/"
chmod +x "$STAGE/$NAME/START-MAC.command" "$STAGE/$NAME/scripts/"*.sh
(cd "$STAGE" && zip -qr "$OUT/$NAME.zip" "$NAME" -x "*/__pycache__/*")
echo "==> $OUT/$NAME.zip"
