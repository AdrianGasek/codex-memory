$ErrorActionPreference = "Stop"

Write-Host "Checking TypeScript..."
bun run typecheck

Write-Host "Building distributable packages..."
bun run build

Write-Host "Checking Python tests..."
uv run --project apps/api pytest apps/api/tests

Write-Host "Validating JSON manifests..."
Get-Content plugins/codex-mem/.codex-plugin/plugin.json -Raw | ConvertFrom-Json | Out-Null
Get-Content .agents/plugins/marketplace.json -Raw | ConvertFrom-Json | Out-Null
Get-Content shared/schemas/memory.schema.json -Raw | ConvertFrom-Json | Out-Null

Write-Host "Smoke checks completed."
