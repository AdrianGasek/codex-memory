# Windows Install

Use PowerShell or Windows Terminal from the project that should receive memory:

```powershell
npx codex-memory install
codex-memory doctor
```

If PowerShell cannot resolve `npx`, call the Windows command shim directly:

```powershell
npx.cmd codex-memory install
```

The installer creates a local runtime under `%USERPROFILE%\.codex-mem`, writes
project config into `.codex/mem.config.json`, installs the Codex plugin config,
and starts the local memory API worker.

Check the worker:

```powershell
codex-memory status
codex-memory doctor
```

If the API is offline, restart it:

```powershell
codex-memory restart
```

Common Windows fixes:

- Use `npx.cmd` when PowerShell aliases or execution policy interfere with
  `npx`.
- Keep `%USERPROFILE%\.codex-mem` out of synced or restricted folders when
  possible.
- Run `codex-memory doctor` after install; it prints the API URL, runtime path,
  SQLite path, MCP server path, plugin config, hooks file, and worker port.
- If port `8000` is busy, rerun install or restart; the worker can use another
  local port and writes that API URL into its state.
