# Codex-Mem Roadmap

Status date: 2026-04-29

This is the working checklist for turning Codex-Mem into a full "brain" for Codex. Update checkboxes only after the feature exists in the repo and the relevant smoke/test path passes.

## How To Use This List

- [x] Keep this file in `.codex/ROADMAP.md` as the project control list.
- [ ] Before starting work, read this file plus `.codex/context/*.md`.
- [ ] After finishing a feature, mark it `[x]`, add a short note if needed, and run the matching tests.
- [ ] Store durable implementation decisions through Codex-Mem once auto-capture or manual capture is available.

## Current Focus

- [x] Implement automatic extractor from the `Stop` hook.
- [x] Replace simple keyword score with a stronger hybrid ranking layer.
- [x] Add memory history/versioning so updates are auditable.
- [x] Add conflict detection and latest-wins resolution.
- [x] Add observability for "what was injected and why".

## 1. Foundation And Project Setup

- [x] Create monorepo structure: `apps/cli`, `apps/mcp-server`, `apps/api`, `shared`, `infra`, `plugins`.
- [x] Add root configs: `package.json`, `tsconfig.base.json`, `.gitignore`, `.env.example`, `docker-compose.yml`.
- [x] Add local data layout: `data/db`, `data/vectors`.
- [x] Add repo-local Codex plugin scaffold under `plugins/codex-mem`.
- [x] Add repo marketplace entry under `.agents/plugins/marketplace.json`.
- [x] Add basic README and project orientation files.
- [x] Add smoke script for TypeScript, Python tests, and JSON manifest validation.
- [x] Add CI workflow for typecheck, tests, and smoke checks.
- [x] Add release/build scripts for distributable CLI and MCP packages.

## 2. Core Memory Engine

- [x] Persist memory entries in SQLite.
- [x] Create structured memory types: `fact`, `decision`, `bug`, `solution`, `pattern`.
- [x] Store required fields: `type`, `title`, `context`, `resolution`, `confidence`, `tags`, `source`, `timestamp`, `project`.
- [x] Add basic deduplication by normalized content hash.
- [x] Add tag support.
- [x] Add project namespace field.
- [x] Add file/path scope for memory entries.
- [x] Add durable history/version table for memory changes.
- [ ] Add update/edit memory endpoint and CLI command.
- [x] Add explicit conflict model: conflicting entry links, superseded status, latest-wins policy.
- [x] Add usage counters: retrieved count, injected count, last used timestamp.
- [x] Add priority fields: importance, confidence decay, manual pinning.

## 3. Retrieval And Ranking

- [x] Add keyword search fallback.
- [x] Add filters for project, tag, and memory type.
- [x] Add context injection endpoint.
- [x] Add basic token-budget-aware trimming.
- [x] Return ranking score in search responses.
- [ ] Add date/time filters.
- [x] Extract ranking into a dedicated ranking module.
- [x] Implement hybrid ranking: keyword score + recency + confidence + importance + usage.
- [x] Add query normalization and stopword handling.
- [x] Add exact-match boost for files, symbols, errors, and commands.
- [ ] Add top-N retrieval profiles for short, normal, and deep modes.
- [ ] Add semantic embeddings search.
- [ ] Add vector store adapter behind a stable interface.
- [ ] Add optional pgvector/Chroma backend.
- [ ] Add summarization when retrieved memory exceeds budget.
- [ ] Add progressive disclosure: compact index first, full details by ID.

## 4. Capture And Extraction

- [x] Add manual capture through CLI `remember`.
- [x] Add MCP `store_memory`.
- [x] Add standardized memory payload validation.
- [ ] Add CLI alias `/note` or `note`.
- [x] Implement `Stop` hook extractor from latest assistant message.
- [ ] Capture "what worked" and "what failed" from assistant responses.
- [ ] Capture memory from tool errors and runtime failures.
- [ ] Capture memory from git diff after code changes.
- [ ] Capture memory from commits.
- [ ] Normalize extracted observations into memory entries.
- [ ] Filter low-value capture: small talk, guesses, temporary logs, obvious facts.
- [ ] Detect duplicate and near-duplicate extracted memories.
- [ ] Detect conflicts during capture.
- [ ] Add approval mode for auto-captured memory before storing.
- [ ] Add passive mode where capture suggestions are shown but not stored.

## 5. Codex Integration And Agent Flow

- [x] Add `SessionStart` hook scaffold.
- [x] Add `UserPromptSubmit` hook scaffold.
- [x] Add `Stop` hook scaffold.
- [x] Inject relevant memory as additional Codex context.
- [x] Add local plugin metadata and skill for memory search.
- [x] Add plugin MCP config.
- [ ] Add `PostToolUse` hook for tool-result capture.
- [ ] Add mode config: passive, active, debug.
- [ ] Add per-project hook enable/disable settings.
- [ ] Add automatic startup checks for API availability.
- [ ] Add graceful degraded mode when API is offline.
- [ ] Add visible debug output showing injected entries.
- [ ] Add command examples for installing/enabling repo-local plugin in Codex.

## 6. MCP And External Memory Server

- [x] Implement MCP `store_memory`.
- [x] Implement MCP `query_memory`.
- [x] Implement MCP `delete_memory`.
- [x] Verify MCP smoke path over stdio.
- [ ] Add MCP `get_memory` by ID.
- [ ] Add MCP `timeline` around a memory or query.
- [ ] Add MCP `get_observations` batch fetch for progressive disclosure.
- [ ] Add MCP `update_memory`.
- [ ] Add MCP `debug_injection`.
- [ ] Add server capability tests and protocol fixtures.
- [ ] Add support for remote HTTP MCP deployment.
- [ ] Add compatibility notes for Cursor, Claude Code, and other agents.

## 7. Smart Memory Layer

- [ ] Detect repeated errors across sessions.
- [ ] Detect frequently reused solutions.
- [ ] Promote stable high-value memories into best practices.
- [ ] Detect anti-patterns from repeated failures.
- [ ] Add summary memory generation.
- [ ] Add stale memory decay.
- [ ] Add automatic archival of low-confidence or unused memory.
- [ ] Add memory consolidation job.
- [ ] Add cross-entry linking: bug -> solution -> pattern.
- [ ] Add confidence recalculation from usage and validation.

## 8. Memory Format And Exports

- [x] Add JSON schema in `shared/schemas/memory.schema.json`.
- [x] Export human-readable `.codex/MEMORY.md`.
- [x] Export `.codex/INDEX.json`.
- [x] Maintain `.codex/SOUL.md` and `.codex/CONTEXT.md`.
- [x] Add `.codex/HISTORY.json` or equivalent history export.
- [ ] Add Markdown import back into SQLite.
- [ ] Add round-trip tests for Markdown export/import.
- [ ] Add repo-sync mode for selected memory entries.
- [ ] Add global memory scope outside a single project.
- [ ] Add memory migration/version metadata.

## 9. Configuration

- [x] Add `.env.example`.
- [x] Add env config for API URL, DB path, project, inject limit, token budget.
- [x] Add Docker config for API and MCP.
- [ ] Add first-class config file, e.g. `.codex/mem.config.json`.
- [ ] Add per-project rules for what to save and ignore.
- [ ] Add path ignore filters for logs, generated files, secrets, and vendor directories.
- [ ] Add sensitivity levels for capture.
- [ ] Add model/provider config for embeddings and summarization.
- [ ] Add debug/verbose config.
- [ ] Add config validation and helpful diagnostics.

## 10. Debug And Observability

- [x] Add CLI `debug` command.
- [x] Show basic injected context from CLI debug.
- [x] Add API endpoint for latest injection trace.
- [x] Record which entries were injected into each turn.
- [x] Record why each entry was ranked highly.
- [ ] Add search/ranking debug view.
- [ ] Add capture debug log.
- [ ] Add manual delete/edit audit log.
- [ ] Add local web viewer for memory stream and search.
- [ ] Add health diagnostics for API, DB, MCP, hooks, and plugin config.

## 11. Security And Safety

- [x] Add basic regex redaction for OpenAI-like keys and secret-looking assignments.
- [ ] Expand secret redaction patterns.
- [ ] Add PII redaction checks.
- [ ] Add private/no-store tags for user prompts and responses.
- [ ] Add path-based no-store rules.
- [ ] Add opt-in sync/share only.
- [ ] Add local/global/team scope isolation.
- [ ] Add encrypted-at-rest option for local DB.
- [ ] Add tests proving secrets are not stored.
- [ ] Add safe failure behavior when redaction fails.

## 12. Power Features

- [ ] Git integration: auto-memory from commits.
- [ ] Git integration: auto-memory from PR/review feedback.
- [ ] CI/CD integration: store build and test failures.
- [ ] Runtime log integration.
- [ ] Cross-project learning.
- [ ] Team memory backend.
- [ ] Shared memory namespaces.
- [ ] Import from Claude-Mem exports if available.
- [ ] Migration assistant from Markdown-only memory.

## 13. Acceptance Milestones

- [x] MVP-0: Skeleton exists and smoke tests pass.
- [ ] MVP-1: Stop hook auto-captures useful memories with filters.
- [ ] MVP-2: Hybrid ranking beats simple keyword search in local fixtures.
- [ ] MVP-3: Memory history, conflicts, and updates are auditable.
- [ ] MVP-4: Debug trace explains every injected memory.
- [ ] MVP-5: Semantic search works with optional vector backend.
- [ ] Beta: Agent can run multiple sessions and demonstrably reuse prior decisions without manual copy/paste.
- [ ] Full Brain: Codex-Mem captures, ranks, compresses, injects, audits, and evolves memory with low noise and safe defaults.
