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

## Memory Files

SQLite is the source of truth. The API also exports a readable `.codex/MEMORY.md` and `.codex/INDEX.json`. `.codex/SOUL.md` and `.codex/CONTEXT.md` are created as human-editable companions.
