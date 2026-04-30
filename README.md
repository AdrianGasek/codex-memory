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
```

## Agent Compatibility

Codex uses the repo-local plugin metadata in `plugins/codex-mem/.codex-plugin/plugin.json` and the MCP server config in `plugins/codex-mem/.mcp.json`.

Cursor, Claude Code, and other MCP-capable agents can connect to the same tools over stdio:

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

Agents or deployments that need a remote endpoint can run the MCP server over HTTP:

```powershell
$env:CODEX_MEM_MCP_TRANSPORT = "http"
$env:CODEX_MEM_MCP_HOST = "0.0.0.0"
$env:CODEX_MEM_MCP_PORT = "3333"
bun run apps/mcp-server/src/server.ts
```

The HTTP transport exposes `GET /health` and JSON-RPC `POST /mcp`; keep the API service reachable through `CODEX_MEM_API_URL`.

## Memory Files

SQLite is the source of truth. The API also exports a readable `.codex/MEMORY.md` and `.codex/INDEX.json`. `.codex/SOUL.md` and `.codex/CONTEXT.md` are created as human-editable companions.
