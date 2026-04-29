# MEMORY

Generated from SQLite. Edit through Codex-Mem commands when possible.

## Injection observability records trace rows

- id: `mem_0ead0b3d14c2`
- type: `solution`
- confidence: `0.95`
- importance: `0.85`
- pinned: `False`
- file_paths: ``
- source: `codex-session`
- project: `codex-brain`
- timestamp: `2026-04-29T10:51:31.258248+00:00`
- status: `active`
- superseded_by: ``
- conflict_ids: ``
- retrieved_count: `0`
- injected_count: `0`
- last_used_timestamp: ``
- tags: `observability, injection, debug`

### Context

Codex-Mem needs to explain what memory was injected into a turn and why.

### Resolution

Store each injection in injection_traces with query, limits, candidate count, injected entries, scores, and ranking reasons; expose the latest trace at GET /memory/debug/injection and include it in /memory/inject responses.

## Conflicting memories use latest-wins status metadata

- id: `mem_851c9edb9981`
- type: `decision`
- confidence: `0.95`
- importance: `0.85`
- pinned: `False`
- file_paths: ``
- source: `codex-session`
- project: `codex-brain`
- timestamp: `2026-04-29T10:49:09.096240+00:00`
- status: `active`
- superseded_by: ``
- conflict_ids: ``
- retrieved_count: `0`
- injected_count: `0`
- last_used_timestamp: ``
- tags: `conflicts, latest-wins, sqlite`

### Context

Codex-Mem needs conflict handling before full update/edit support exists.

### Resolution

When storing a new active memory with the same type, project, and normalized title, mark older active entries superseded, set their superseded_by to the new ID, and store conflict_ids links on both sides through history snapshots.

## Memory entries support file path scopes

- id: `mem_760768f44c1e`
- type: `solution`
- confidence: `0.95`
- importance: `0.80`
- pinned: `False`
- file_paths: `apps/api/app/storage/sqlite.py, apps/api/app/core/models.py, apps/cli/src/client/memoryClient.ts, apps/mcp-server/src/server.ts`
- source: `codex-session`
- project: `codex-brain`
- timestamp: `2026-04-29T10:55:09.986007+00:00`
- status: `active`
- superseded_by: ``
- conflict_ids: ``
- retrieved_count: `0`
- injected_count: `0`
- last_used_timestamp: ``
- tags: `path-scope, retrieval, sqlite`

### Context

Codex-Mem needs memories to apply to specific files or directories for retrieval and conflict handling.

### Resolution

Use file_paths on MemoryCreate/MemoryEntry, store it as JSON in SQLite, include it in exports and ranking text, support search filtering with path, and only supersede same-title memories when their scopes overlap or one side is unscoped.

## Memory history uses immutable snapshots

- id: `mem_4a5119f9514a`
- type: `solution`
- confidence: `0.95`
- importance: `0.80`
- pinned: `False`
- file_paths: ``
- source: `codex-session`
- project: `codex-brain`
- timestamp: `2026-04-29T10:42:50.769232+00:00`
- status: `active`
- superseded_by: ``
- conflict_ids: ``
- retrieved_count: `0`
- injected_count: `0`
- last_used_timestamp: ``
- tags: `history, audit, sqlite`

### Context

Codex-Mem needs auditable memory changes without depending on future edit support.

### Resolution

Create memory_history with per-memory versions and record create/delete snapshots transactionally; export .codex/HISTORY.json and expose GET /memory/history.
