#!/usr/bin/env bash
set -euo pipefail

bun run typecheck
bun run build
uv run --project apps/api pytest apps/api/tests
python -m json.tool plugins/codex-mem/.codex-plugin/plugin.json >/dev/null
python -m json.tool .agents/plugins/marketplace.json >/dev/null
python -m json.tool shared/schemas/memory.schema.json >/dev/null

echo "Smoke checks completed."
