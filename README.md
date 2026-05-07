<p align="center">
  <img src="./logo.png" alt="Codex-Mem logo" width="160">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/v/codex-memory?style=flat-square&label=npm" alt="npm version"></a>
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/dw/codex-memory?style=flat-square&label=downloads" alt="npm weekly downloads"></a>
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/l/codex-memory?style=flat-square" alt="license"></a>
  <img src="https://img.shields.io/node/v/codex-memory?style=flat-square" alt="node version">
  <img src="https://img.shields.io/npm/types/codex-memory?style=flat-square" alt="TypeScript types">
</p>

# Codex-Mem

Persistent, local-first memory for Codex agents.

Codex-Mem stores reusable project knowledge in SQLite, exposes it through CLI, HTTP API, MCP tools, and Codex hooks, then injects the most relevant context into future Codex sessions.

## Install In A Codex Project

Run this inside the repository where you want Codex memory enabled:

```bash
npx codex-memory install
codex-memory doctor
codex-memory status
```

The installer:

- creates `.codex/mem.config.json`
- adds the Codex plugin entry to `.agents/plugins/marketplace.json`
- installs runtime files under `~/.codex-mem`
- starts the local memory API
- wires the plugin hooks and MCP server to that runtime

After install, restart Codex or reload the workspace so it can discover the plugin metadata.

## Use The Library

Add a memory:

```bash
codex-memory remember \
  --type decision \
  --title "Use SQLite for local storage" \
  --context "Project memory MVP" \
  --resolution "Keep canonical memory in SQLite and use local embeddings by default."
```

Query memory:

```bash
codex-memory query "SQLite storage"
codex-memory debug --query "current task"
codex-memory get <memory-id>
```

Manage the local worker:

```bash
codex-memory status
codex-memory restart
codex-memory stop
codex-memory start
```

Remove the plugin from a project:

```bash
codex-memory uninstall
```

## Codex Plugin Setup For Developers

Use this path when you are developing this repository or testing the repo-local plugin scaffold.

1. Install dependencies:

```bash
bun install
uv sync --project apps/api
```

2. Start the API:

```bash
bun run api:dev
```

3. In another terminal, start the MCP server:

```bash
bun run mcp:dev
```

4. Point Codex at the repo-local plugin.

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

5. Make sure the API URL is available to hooks and MCP:

```powershell
$env:CODEX_MEM_API_URL = "http://127.0.0.1:8000"
$env:CODEX_MEM_HOOKS_ENABLED = "true"
$env:CODEX_MEM_MODE = "active"
```

6. Verify the setup:

```bash
bun run cli dev doctor
bun run cli remember --type fact --title "Plugin smoke" --context "Repo-local plugin setup works."
bun run cli query "Plugin smoke"
```

For a real consumer project, prefer `npx codex-memory install`; it copies built runtime assets to `~/.codex-mem` and writes an absolute plugin path, so the consuming repo does not depend on this checkout.

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

Memory data is local by default. Do not store secrets, tokens, credentials, or private personal data as memory.

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

## Troubleshooting

- `npx` fails on Windows PowerShell: try `npx.cmd codex-memory install`.
- API is offline: run `codex-memory doctor`, then `codex-memory restart`.
- Port `8000` is busy: the installer reuses a healthy API or selects another local port.
- MCP tools fail: check `codex-memory doctor` and confirm `CODEX_MEM_API_URL`.
- Hooks are silent: confirm `CODEX_MEM_HOOKS_ENABLED=true` and restart Codex.
- Runtime looks broken: rerun `npx codex-memory install` in the target project.

## Status

Codex-Mem is a local-first beta. SQLite is the source of truth; optional vector backends are index backends, not replacements for SQLite. Team/shared memory exists as local namespaces, not as a hosted synchronization or authorization service.
