# Codex-Mem

Codex-Mem is a repo-local persistent memory layer for Codex agents. It stores reusable project knowledge in SQLite, exposes it through an HTTP API, CLI, MCP tools, and Codex hooks, then injects the most relevant memory back into future sessions.

## Components

- `apps/api` - FastAPI service with SQLite storage and Markdown export.
- `apps/cli` - TypeScript CLI for `remember`, `query`, and `debug`.
- `apps/mcp-server` - stdio MCP server exposing memory tools.
- `plugins/codex-mem` - repo-local Codex plugin scaffold with hooks and MCP config.
- `shared/schemas` and `shared/prompts` - shared memory shape and prompt templates.

## Quick Start

```bash
bun install
uv sync --project apps/api
uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
bun run cli remember --type decision --title "Use SQLite first" --context "MVP storage" --resolution "Embeddings move to v2."
bun run cli query "SQLite"
bun run cli debug
```

## Operating The API

Start the local API from the repository root:

```powershell
$env:CODEX_MEM_API_URL = "http://127.0.0.1:8000"
uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Stop the API with `Ctrl+C` in the terminal running `uvicorn`. Confirm shutdown or readiness with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

On Windows, if PowerShell blocks `npm.ps1`, use `npm.cmd` directly:

```powershell
npm.cmd install
```

## API

- `GET /health`
- `POST /memory`
- `GET /memory/search?query=...`
- `GET /memory/inject?query=...`
- `DELETE /memory/{id}`

## Current Guarantees

Codex-Mem stores canonical memory entries in repo-local SQLite, exports readable Markdown/JSON companion files, supports local semantic search, and exposes memory through HTTP, CLI, MCP stdio, MCP HTTP, and Codex hooks. Markdown import is bounded to the repository by default, external imports require explicit opt-in, and team/shared scopes are namespace-isolated with tests for access boundaries. Optional Chroma and pgvector modes use explicit backend clients and fail closed unless local fallback is configured.

## Known Limitations

The project remains a local-first beta rather than a hardened multi-tenant service. Team memory is a local namespace contract, not a remote authorization service. Shared namespaces are created implicitly by writes and do not yet have lifecycle administration APIs. SQLite encryption protects selected text fields only when explicitly enabled with an operator key; Markdown exports, process memory, logs, and environment variables are outside that protection. External vector backends require separately running services and are covered by mocked contract tests plus documented local smoke commands.

## MCP Tools

- `store_memory`
- `query_memory`
- `delete_memory`

## Repo-local Codex Plugin

From the repository root, start the API used by hooks and MCP:

```powershell
$env:CODEX_MEM_API_URL = "http://127.0.0.1:8000"
uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The local plugin is declared in `.agents/plugins/marketplace.json` and points at `./plugins/codex-mem`. Enable that repo-local plugin in Codex, then verify the MCP server command from the plugin manifest:

```powershell
bun run apps/mcp-server/src/server.ts
```

Useful per-project hook settings:

```powershell
$env:CODEX_MEM_MODE = "active"          # active, passive, or debug
$env:CODEX_MEM_HOOKS_ENABLED = "true"   # false disables all Codex-Mem hooks
$env:CODEX_MEM_DISABLED_HOOKS = ""      # comma-separated: session-start,user-prompt,stop,post-tool-use
$env:CODEX_MEM_DEBUG_VERBOSE = "false"  # true adds API, limit, and token budget details to debug hook output
$env:CODEX_MEM_CAPTURE_DEBUG_LOG_ENABLED = "false"
$env:CODEX_MEM_CAPTURE_DEBUG_LOG = ".codex/CAPTURE_DEBUG.jsonl"
$env:CODEX_MEM_SYNC_ENABLED = "false"                  # true opts in to repo sync/share operations
$env:CODEX_MEM_SYNC_SCOPE = "local"
$env:CODEX_MEM_VECTOR_BACKEND = "local"                # local, chroma, or pgvector
$env:CODEX_MEM_VECTOR_ALLOW_LOCAL_FALLBACK = "false"   # true explicitly degrades external vector backends to local
$env:CODEX_MEM_CHROMA_URL = "http://127.0.0.1:8000"
$env:CODEX_MEM_CHROMA_COLLECTION = "codex_mem"
$env:CODEX_MEM_CHROMA_TIMEOUT_SECONDS = "5"
$env:CODEX_MEM_DB_ENCRYPTION_ENABLED = "false"
$env:CODEX_MEM_DB_ENCRYPTION_KEY = ""                  # required when DB encryption is enabled
```

Codex hooks require a reachable API service, `CODEX_MEM_API_URL`, the repo-local plugin metadata in `.agents/plugins/marketplace.json`, and `CODEX_MEM_HOOKS_ENABLED=true` unless a deployment intentionally runs without hooks. In degraded mode, hooks should avoid writes when the API is offline and surface diagnostics instead of failing the agent workflow.

Mode summary: `active` captures and injects through the API, `passive` shows capture suggestions without storing them, `approval` requires review before auto-captured memory is persisted, `debug` adds verbose diagnostics, and degraded mode is entered when hooks or MCP cannot reach the API.

### Local Database Encryption Status

The current local DB protection option is legacy content hiding for selected SQLite text fields, not production-grade encryption at rest. The target production design is documented in `.codex/feedback-review/encryption-decision.md`: application-level field encryption with Python `cryptography`, an operator-supplied `CODEX_MEM_DB_ENCRYPTION_KEY`, authenticated failure for wrong keys or damaged ciphertext, and an explicit key-rotation migration.

Until that implementation is complete, do not treat the SQLite file, Markdown exports, logs, or process environment as safe places for secrets.

### SQLite Schema Migration Recovery

When Codex-Mem opens an existing SQLite database with an older `schema_version`, it writes a sibling backup before applying metadata or schema updates. The backup name uses the pattern `codex-mem.sqlite3.v<old>-to-v<new>.bak`.

To recover manually, stop the API, move the current database aside, copy the matching backup back to the configured DB path, and restart the API with the previous compatible code/configuration. Keep the moved current database until you have confirmed the restored database contains the expected memories.

### Vector Backend Storage Model

SQLite is the source of truth for memory entries and stores the local embedding cache used by the `local` backend. External vector backends such as Chroma and pgvector are index backends: they store embedding records keyed by memory id, document text, and non-secret routing metadata for similarity search, while the canonical memory payload remains in SQLite. If an external backend is unavailable, Codex-Mem reports a clear backend error. Set `vector.allow_local_fallback` or `CODEX_MEM_VECTOR_ALLOW_LOCAL_FALLBACK=true` only when local semantic search is an acceptable explicit degraded mode.

- `local` uses deterministic local embeddings stored in SQLite and requires no external service.
- `chroma` means a Chroma index backend is required; without a real Chroma client it fails closed unless explicit local fallback is enabled.
- `pgvector` means a Postgres database with pgvector support is required; without a real pgvector client it fails closed unless explicit local fallback is enabled.

Run a local Chroma service for development:

```powershell
docker run --rm -p 8000:8000 chromadb/chroma
$env:CODEX_MEM_VECTOR_BACKEND = "chroma"
$env:CODEX_MEM_CHROMA_URL = "http://127.0.0.1:8000"
$env:CODEX_MEM_CHROMA_COLLECTION = "codex_mem"
```

Run local Postgres with pgvector for development:

```powershell
docker run --rm -p 5432:5432 `
  -e POSTGRES_USER=codex `
  -e POSTGRES_PASSWORD=codex `
  -e POSTGRES_DB=codex_mem `
  pgvector/pgvector:pg16
$env:CODEX_MEM_VECTOR_BACKEND = "pgvector"
$env:CODEX_MEM_PGVECTOR_DSN = "postgresql://codex:codex@127.0.0.1:5432/codex_mem"
```

Minimal smoke after selecting either external backend:

```powershell
uv run --project apps/api pytest apps/api/tests/test_memory_api.py -k "vector_backend or chroma or pgvector"
uv run --project apps/api uvicorn app.main:app --host 127.0.0.1 --port 8000
bun run cli remember --type fact --title "Vector smoke" --context "External vector backend is configured."
bun run cli query "vector backend"
```

## Agent Compatibility

Codex uses the repo-local plugin metadata in `plugins/codex-mem/.codex-plugin/plugin.json` and the MCP server config in `plugins/codex-mem/.mcp.json`.

### MCP stdio

Cursor, Claude Code, and other MCP-capable agents can connect to the same tools over stdio. The stdio server expects `CODEX_MEM_API_URL` to point at a running API service:

```json
{
  "mcpServers": {
    "codex-mem": {
      "command": "bun",
      "args": ["run", "apps/mcp-server/src/server.ts"],
      "env": {
        "CODEX_MEM_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

### MCP HTTP

Agents or deployments that need a remote endpoint can run the MCP server over HTTP:

```powershell
$env:CODEX_MEM_MCP_TRANSPORT = "http"
$env:CODEX_MEM_MCP_HOST = "0.0.0.0"
$env:CODEX_MEM_MCP_PORT = "3333"
bun run apps/mcp-server/src/server.ts
```

The HTTP transport exposes `GET /health` and JSON-RPC `POST /mcp`; keep the API service reachable through `CODEX_MEM_API_URL`.

## Troubleshooting

- API unavailable: run `Invoke-RestMethod http://127.0.0.1:8000/health`, verify `CODEX_MEM_API_URL`, then restart `uvicorn`.
- Hook injection is empty: run `bun run cli debug --query "project memory"` and inspect `/memory/health/diagnostics`.
- MCP tools fail: verify `bun run apps/mcp-server/src/server.ts` starts and that the MCP process inherits `CODEX_MEM_API_URL`.
- Config warnings: call `GET /memory/config/diagnostics` or run `bun run cli debug`.
- Docker smoke blocked: start Docker Desktop or another Docker daemon, then rerun the Docker build commands from `.codex/feedback-review/closure-roadmap.md`.
- Encryption startup failure: set `CODEX_MEM_DB_ENCRYPTION_KEY` when `CODEX_MEM_DB_ENCRYPTION_ENABLED=true`.

## Memory Files

SQLite is the source of truth. The API also exports a readable `.codex/MEMORY.md` and `.codex/INDEX.json`. `.codex/SOUL.md` and `.codex/CONTEXT.md` are created as human-editable companions.

## Team Memory Model

Team memory is currently a local namespaced mode inside the same SQLite store, not a remote shared service or automatic synchronization backend. `team.id` or `CODEX_MEM_TEAM_ID` identifies the tenant namespace; entries are isolated by a `team:<id>` project namespace and are only returned through team-aware APIs when the caller is configured for that team. `team.role` or `CODEX_MEM_TEAM_ROLE` is one of `reader`, `writer`, or `admin`: readers can search, writers can create team entries, and admins are reserved for namespace management. Future sync backends can mirror this namespace model, but sync remains opt-in and separate from local team reads and writes.

Project-local memory uses the configured project name, global memory uses `global`, shared namespaces use `shared:<name>`, and team memory uses `team:<id>`. Default project searches may include global entries, but team and shared APIs do not mix entries from other teams, shared namespaces, or local projects unless a future explicit policy says so.

Team write, update, delete, and future sync/share operations must write audit entries with the action, memory id, team id, source, project namespace, and timestamp. Team search is read-only and is covered by access-control tests rather than audit entries.

Example team configuration:

```powershell
$env:CODEX_MEM_TEAM_BACKEND = "local"
$env:CODEX_MEM_TEAM_ID = "default"
$env:CODEX_MEM_TEAM_ROLE = "reader"          # reader, writer, or admin
$env:CODEX_MEM_TEAM_WRITE_ENABLED = "false"  # true is required for project=team:<id> writes
```

## Shared Namespaces

Shared namespace names are normalized to lowercase slugs containing letters, numbers, `-`, and `_`; path separators and other punctuation become `-`, and empty names are rejected. A shared namespace maps to the project namespace `shared:<name>` and is isolated from local, global, and team scopes unless a future explicit policy changes that behavior.

Namespaces are created implicitly when a memory entry is written with `project=shared:<name>`. There is no separate namespace create/delete API yet; removing all entries from a namespace removes it from `GET /memory/shared/namespaces`.
