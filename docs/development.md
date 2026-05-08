# Development

This guide is for contributors working on the Codex-Mem repository itself. If you only want to use Codex-Mem in another project, start with the root README.

## Repository Setup

Install dependencies:

```bash
bun install
uv sync --project apps/api
```

Start the API:

```bash
bun run api:dev
```

In another terminal, start the MCP server:

```bash
bun run mcp:dev
```

## Repo-Local Plugin

The local marketplace file is already present at `.agents/plugins/marketplace.json` and points to:

```text
./plugins/codex-mem
```

The plugin contains:

- `.codex-plugin/plugin.json` - Codex plugin metadata
- `.mcp.json` - MCP server command
- `hooks.json` - Codex hook commands
- `scripts/hook_memory.py` - hook runner
- `skills/mem-search/SKILL.md` - memory search skill

Make sure the API URL is available to hooks and MCP:

```powershell
$env:CODEX_MEM_API_URL = "http://127.0.0.1:8000"
$env:CODEX_MEM_HOOKS_ENABLED = "true"
$env:CODEX_MEM_MODE = "active"
```

Verify the repo-local setup:

```bash
bun run cli dev doctor
bun run cli remember --type fact --title "Plugin smoke" --context "Repo-local plugin setup works."
bun run cli query "Plugin smoke"
```

For a real consumer project, prefer:

```bash
npx codex-memory install
```

The installer copies built runtime assets to `~/.codex-mem` and writes an absolute plugin path, so the consuming repo does not depend on this checkout.

## MCP Tools

Codex-Mem exposes these MCP tools:

- `query_memory`
- `store_memory`
- `delete_memory`

The installed plugin writes an MCP config similar to:

```json
{
  "mcpServers": {
    "codex-memory": {
      "command": "bun",
      "args": ["<runtime>/mcp-server/dist/server.js"],
      "env": {
        "CODEX_MEM_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

## Configuration

Project config lives in `.codex/mem.config.json`.

Common environment variables:

```bash
CODEX_MEM_API_URL=http://127.0.0.1:8000
CODEX_MEM_HOME=~/.codex-mem
CODEX_MEM_MODE=active
CODEX_MEM_HOOKS_ENABLED=true
CODEX_MEM_VECTOR_BACKEND=local
```

## Repository Layout

- `apps/api` - FastAPI memory API and SQLite storage
- `apps/cli` - `codex-memory` CLI, installer, worker management, and diagnostics
- `apps/mcp-server` - MCP stdio/HTTP server exposing memory tools
- `plugins/codex-mem` - repo-local Codex plugin scaffold
- `shared/schemas` - shared memory schemas
- `shared/prompts` - prompt templates for capture and injection
- `docs` - longer product documentation

## API

Useful local endpoints:

- `GET /health`
- `POST /memory`
- `GET /memory/search?query=...`
- `GET /memory/inject?query=...`
- `DELETE /memory/{id}`

## Test And Release Checks

```bash
bun run typecheck
bun run cli:test
bun run api:test
bun run pack:smoke
```

## Publishing To npm

This repository is a monorepo. The root `package.json` is private and exists for development tasks, workspaces, and shared build scripts. It is not the npm package users install.

The public npm package is `apps/cli/package.json`, which publishes the `codex-memory` CLI plus the staged runtime files needed by installed projects.

Publish from the CLI package directory:

```bash
cd apps/cli
npm pack --dry-run
npm publish --access public
```

Before publishing, confirm the dry run includes `README.md`, `dist`, `runtime`, `LICENSE`, and `package.json`.

## Troubleshooting

- `npx` fails on Windows PowerShell: try `npx.cmd codex-memory install`.
- `npm i codex-memory` fails inside this source checkout: use `bun install` for repo development, or run `npx codex-memory install` from a separate target project.
- API is offline: run `codex-memory doctor`, then `codex-memory restart`.
- Port `8000` is busy: the installer reuses a healthy API or selects another local port.
- MCP tools fail: check `codex-memory doctor` and confirm `CODEX_MEM_API_URL`.
- Hooks are silent: confirm `CODEX_MEM_HOOKS_ENABLED=true` and restart Codex.
- Runtime looks broken: rerun `npx codex-memory install` in the target project.
