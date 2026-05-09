# MCP Integration

Codex-memory exposes memory tools through the packaged MCP server. The normal
install path writes the MCP config automatically:

```bash
npx codex-memory install
codex-memory doctor
```

## Tools

- `query_memory` searches relevant project memory.
- `store_memory` stores validated durable memory.
- `get_memory` fetches a memory by ID.
- `update_memory` edits an existing memory and records history.
- `delete_memory` removes a memory.
- `timeline` returns related history around a memory or query.
- `get_observations` fetches full details for progressive disclosure.
- `debug_injection` explains what would be injected and why.

## API URL

MCP calls the local API through `CODEX_MEM_API_URL`. The default is:

```bash
CODEX_MEM_API_URL=http://127.0.0.1:8000
```

Run `codex-memory doctor` to see the actual API URL, especially if the worker
selected a different port.

## stdio Mode

Installed projects use stdio by default. The generated config points at the
staged MCP server:

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

## HTTP Mode

The API is HTTP-first and runs locally. Use HTTP mode for direct integration
tests or adjacent tools that call the API instead of MCP stdio:

```bash
curl http://127.0.0.1:8000/health
curl "http://127.0.0.1:8000/memory/search?query=SQLite"
```

## Minimal Smoke Test

```bash
codex-memory restart
codex-memory doctor
codex-memory remember --type fact --title "MCP smoke" --context "MCP setup"
codex-memory query "MCP smoke"
```

Expected result: `doctor` reports `API: ok`, `MCP server: ok`, `Plugin config:
ok`, and the query returns the saved memory.

## Troubleshooting

- `API: offline`: run `codex-memory restart`, then `codex-memory doctor`.
- `MCP server: missing`: rerun `npx codex-memory install`.
- `Plugin config: missing`: rerun install from the project root.
- Wrong API URL: restart Codex after install so MCP picks up the new env.
- Windows `npx` issues: use `npx.cmd codex-memory install`.
