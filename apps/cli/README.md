# codex-memory

Local persistent memory for Codex agents.

`codex-memory` installs a local memory runtime for a Codex workspace. It stores project knowledge in SQLite, exposes MCP tools, and wires Codex hooks so agents can search, capture, and reuse decisions, fixes, facts, and patterns across sessions.

## Quick Start

```bash
npx codex-memory install
codex-memory doctor
codex-memory remember --type decision --title "Use SQLite" --context "Local memory storage" --resolution "Keep canonical memory in SQLite."
codex-memory query "SQLite"
```

## Common Commands

```bash
codex-memory status
codex-memory restart
codex-memory debug --query "current task"
codex-memory uninstall
```

## Data

Memory is local-first and stored under `~/.codex-mem` by default. Do not store secrets, tokens, credentials, or private personal data as memory.
