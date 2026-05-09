<p align="center">
  <img src="https://raw.githubusercontent.com/AdrianGasek/codex-memory/main/new_gh_banner.png" alt="codex-memory banner">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/v/codex-memory?style=flat-square&label=npm" alt="npm version"></a>
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/dw/codex-memory?style=flat-square&label=downloads" alt="npm weekly downloads"></a>
  <a href="https://www.npmjs.com/package/codex-memory"><img src="https://img.shields.io/npm/l/codex-memory?style=flat-square" alt="license"></a>
  <img src="https://img.shields.io/node/v/codex-memory?style=flat-square" alt="node version">
  <img src="https://img.shields.io/npm/types/codex-memory?style=flat-square" alt="TypeScript types">
</p>

# codex-memory

Project-local memory for Codex agents.

`codex-memory` installs a local memory runtime for a Codex workspace. It stores project knowledge in SQLite, exposes MCP tools, and wires Codex hooks so agents can search, capture, and reuse decisions, fixes, facts, and patterns across sessions.

## Quick Start

```bash
npx codex-memory install
codex-memory doctor
codex-memory remember --type decision --title "Use SQLite" --context "Local memory storage" --resolution "Keep canonical memory in SQLite."
codex-memory query "SQLite"
```

On Windows PowerShell, use `npx.cmd codex-memory install` if `npx` is not
resolved. Run `codex-memory doctor` after install to confirm the API URL,
SQLite path, MCP server, plugin config, hooks, and worker port.

## Common Commands

```bash
codex-memory status
codex-memory restart
codex-memory debug --query "current task"
codex-memory uninstall
```

## Memory Types

Use `fact`, `decision`, `bug`, `solution`, and `pattern` for durable project
knowledge:

```bash
codex-memory remember --type fact --title "Frontend uses Next.js" --context "Application stack"
codex-memory remember --type bug --title "Windows shell cannot resolve npx" --context "PowerShell install path" --resolution "Run npx.cmd codex-memory install."
codex-memory query "PowerShell npx"
```

## MCP

The installer writes MCP configuration for the packaged server. The server uses
`CODEX_MEM_API_URL`, usually `http://127.0.0.1:8000`, and exposes memory tools
such as `query_memory`, `store_memory`, `get_memory`, `update_memory`, and
`delete_memory`.

## Guides

- [Windows install](https://github.com/AdrianGasek/codex-memory/blob/main/docs/windows-install.md)
- [Memory type examples](https://github.com/AdrianGasek/codex-memory/blob/main/docs/memory-types.md)
- [MCP integration](https://github.com/AdrianGasek/codex-memory/blob/main/docs/mcp-integration.md)
- [Team benefits](https://github.com/AdrianGasek/codex-memory/blob/main/docs/team-benefits.md)
- [Comparison with Codex memories](https://github.com/AdrianGasek/codex-memory/blob/main/docs/codex-memories-comparison.md)

## Data

Memory is local-first and stored under `~/.codex-mem` by default. Do not store secrets, tokens, credentials, or private personal data as memory.

## Package Publishing

The GitHub repository is a monorepo. The root `package.json` is private and is used for development, workspaces, and shared scripts.

The npm package users install is published from `apps/cli`, because that directory contains the `codex-memory` CLI manifest, built `dist` files, runtime assets, license, and this README.

```bash
cd apps/cli
npm pack --dry-run
npm publish --access public
```

The dry run should list `README.md` before publishing.
