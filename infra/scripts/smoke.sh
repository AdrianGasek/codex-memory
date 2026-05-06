#!/usr/bin/env bash
set -euo pipefail

BUN_BIN="${BUN_BIN:-bun}"
if ! command -v "$BUN_BIN" >/dev/null 2>&1 && command -v bun.exe >/dev/null 2>&1; then
  BUN_BIN="bun.exe"
fi
UV_BIN="${UV_BIN:-uv}"
if ! command -v "$UV_BIN" >/dev/null 2>&1 && command -v uv.exe >/dev/null 2>&1; then
  UV_BIN="uv.exe"
fi
PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && command -v python.exe >/dev/null 2>&1; then
  PYTHON_BIN="python.exe"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && command -v py.exe >/dev/null 2>&1; then
  PYTHON_BIN="py.exe"
fi

"$BUN_BIN" run typecheck
"$BUN_BIN" run build
"$UV_BIN" run --project apps/api pytest apps/api/tests
(cd apps/api && "$UV_BIN" run python -c "from fastapi.testclient import TestClient; from app.main import app; response = TestClient(app).get('/health'); assert response.status_code == 200 and response.json() == {'status': 'ok'}")
"$PYTHON_BIN" -m json.tool plugins/codex-mem/.codex-plugin/plugin.json >/dev/null
"$PYTHON_BIN" -m json.tool .agents/plugins/marketplace.json >/dev/null
"$PYTHON_BIN" -m json.tool shared/schemas/memory.schema.json >/dev/null

echo "Smoke checks completed."
