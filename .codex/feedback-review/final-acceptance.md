# Final Acceptance

Status date: 2026-05-06

## Validation Commands

- `uv run --project apps/api pytest apps/api/tests` - passed locally.
- `bun run typecheck` - passed locally.
- `bun --cwd apps/cli test` - passed locally.
- `bun run build` - passed locally.
- JSON manifest validation for plugin, marketplace, and memory schema - passed locally.
- `uv run --project apps/api pytest apps/api/tests/test_mcp_server_protocol.py` - passed locally for stdio and HTTP MCP coverage.
- `uv run --project apps/api pytest apps/api/tests/test_stop_hook_capture.py` - passed locally for hook coverage.
- `powershell -ExecutionPolicy Bypass -File infra/scripts/smoke.ps1` - passed locally.
- `bash infra/scripts/smoke.sh` - passed locally.
- `docker build -f infra/docker/api.Dockerfile -t codex-mem-api:closure .` - passed locally.
- `docker build -f infra/docker/mcp.Dockerfile -t codex-mem-mcp:closure .` - passed locally.

## Known Validation Blockers

- None.

## Closed Risks

- P1 encrypted-at-rest claim mismatch: closed by replacing the custom XOR stream with `cryptography` AES-GCM field encryption, documenting the threat model, and adding wrong-key/damaged-ciphertext tests.
- P1 Markdown import arbitrary path read: closed by repository boundary checks, external-path opt-in config, file type/size validation, and refusal tests.
- P2 Chroma/pgvector placeholder risk: closed by explicit backend clients, fail-closed diagnostics, mock contract tests, and documented local smoke commands.
- P2 team backend overclaim: closed by documenting the local namespace model, adding team id/role/write opt-in checks, audit, and isolation tests.
- P3 web viewer router coupling: closed by moving viewer HTML/CSS/JS into static assets served by a thin router.
- API, CLI, MCP, hook, ranking, import, encryption, redaction, team/shared, viewer, and migration behavior are covered by local tests.
- SQLite schema version is `2`; opening an older schema metadata version writes a migration backup and preserves existing memory rows.
- README documents startup, shutdown, plugin configuration, troubleshooting, vector backends, encryption status, and migration recovery.

## Accepted Limitations

- Team memory remains a local namespace backend, not a remote multi-tenant authorization service.
- Shared namespaces are created by writes and do not yet expose lifecycle administration APIs.
- Docker build acceptance has been verified locally after Docker became available.
