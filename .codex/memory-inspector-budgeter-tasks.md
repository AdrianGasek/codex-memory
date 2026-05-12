# Memory Inspector And Budgeter Tasks

Source: `.codex/memory-inspector-budgeter.md`

Use this checklist to turn the observability and context-budgeting proposal into implementation work. Mark items `[x]` only after code exists and matching verification passes.

## MVP 1: Context Injection Preview

- [x] Add a side-effect-free API endpoint for previewing context injection.
- [x] Add a CLI command: `codex-memory inject-preview "task" --budget 4000 --json`.
- [x] Add `preview` as a CLI alias.
- [x] Return selected memories with title, type, relevance, reason, mode, and estimated tokens.
- [x] Return excluded memories with reason and estimated tokens.
- [x] Include rendered `additional_context` so agents can inspect exact injected text.
- [x] Ensure preview does not increment usage counters.
- [x] Ensure preview does not write injection traces.
- [x] Add API tests for preview behavior.
- [x] Add CLI tests for text and JSON output.

## MVP 2: Token Optimizer / Context Budgeter

- [ ] Add `codex-memory optimize-context "task" --budget 6000 --strategy balanced`.
- [ ] Support strategies: `minimal`, `balanced`, `deep`, `safety-first`.
- [ ] Classify selected context as `must_include` or `nice_to_include`.
- [ ] Report selected tokens, skipped tokens, saved-by-dedupe tokens, stale skips, and conflicts.
- [ ] Add budget warnings when selected context is close to or over budget.
- [ ] Add tests for each strategy.

## MVP 3: Memory Usage Stats

- [ ] Add `codex-memory stats`.
- [ ] Add `--project`, `--since`, and `--json` options.
- [ ] Report memory calls by command.
- [ ] Report total injected memories, average injected tokens, max injected tokens, and skipped due to budget.
- [ ] Report most recalled files.
- [ ] Report most used memory types.
- [ ] Add `stats --impact` with memory-assisted sessions, boundary warnings, repeated bug reuse, and average context size.
- [ ] Add API and CLI tests.

## MVP 4: Explain Why This Memory

- [ ] Add `codex-memory explain-memory <memory-id>`.
- [ ] Return ranking reason, matching query terms, file/path evidence, usage evidence, and conflict/staleness signals.
- [ ] Add evidence arrays to `inject-preview` entries when available.
- [ ] Add tests proving explanations are deterministic and redact secrets.

## MVP 5: Memory Health Check

- [ ] Add `codex-memory health`.
- [ ] Report DB, schema, vector backend, hooks, MCP, plugin config, and indexing state.
- [ ] Report stale entries, duplicates, conflicting decisions, and largest memory chunks.
- [ ] Recommend cleanup commands such as `prune`, `compact`, or `dedupe`.
- [ ] Add JSON output for agents.
- [ ] Add tests for healthy, warning, and error states.

## MVP 6: Memory Diff

- [ ] Add `codex-memory diff <base-ref>`.
- [ ] Detect new memory candidates from changed files and commits.
- [ ] Detect outdated memory candidates after code changes.
- [ ] Reuse existing handoff/git-diff capture logic where possible.
- [ ] Add tests with fixture git histories.

## MVP 7: Memory Mode Status

- [ ] Add `codex-memory status --memory-mode`.
- [ ] Report whether memory is indexed, readable, writable, preview-enabled, and budget-limited.
- [ ] Distinguish disabled, read-only, writable, and policy-blocked modes.
- [ ] Add tests for config-driven status output.

## MVP 8: Dashboard TUI

- [ ] Add `codex-memory dashboard`.
- [ ] Include views for current project brain, recent recalls, token usage, risk map, stale memories, top recalled files, and current task scope.
- [ ] Keep a non-interactive `--json` or `--summary` mode for agents and CI.
- [ ] Add smoke tests for dashboard startup.

## MVP 9: Risk Map / Hotspot Graph

- [ ] Add `codex-memory risk-map`.
- [ ] Rank high-risk files by memory type, bug history, co-change frequency, and missing tests.
- [ ] Include reasons for each hotspot.
- [ ] Reuse risk-map output in `safe`, `plan`, and `review` flows.
- [ ] Add tests for deterministic hotspot ordering.

## MVP 10: Session Audit

- [ ] Add `codex-memory audit-session <session-id>`.
- [ ] Show retrieved, injected, skipped, and potentially useful unused memories.
- [ ] Warn when risky files were edited without relevant memory injection.
- [ ] Warn when related memories existed but were not selected.
- [ ] Add tests with recorded injection traces and file-change fixtures.

## MVP 11: Prune / Compact / Dedupe

- [ ] Add `codex-memory prune --stale 90d`.
- [ ] Add `codex-memory prune --low-hit-rate`.
- [ ] Add `codex-memory compact --max-tokens 800`.
- [ ] Add `codex-memory dedupe`.
- [ ] Report removed, compacted, and superseded entries.
- [ ] Require dry-run output before destructive cleanup unless `--yes` is passed.
- [ ] Add tests proving protected/pinned memories are preserved.

## MVP 12: Pin / Never Inject / Promote

- [ ] Add `codex-memory pin <memory-id>`.
- [ ] Add `codex-memory never-inject <memory-id>`.
- [ ] Add `codex-memory mark-stale <memory-id>`.
- [ ] Add `codex-memory promote <memory-id> --to AGENTS.md`.
- [ ] Suggest promotion when a memory is frequently used and looks like a stable project rule.
- [ ] Add tests for pinned, blocked, stale, and promoted memory behavior.

## Documentation And Release

- [ ] Update README with `inject-preview`, budget reports, and JSON examples.
- [ ] Add examples for agents and humans.
- [ ] Add changelog entry for each shipped MVP.
- [ ] Run full verification before release: `bun run typecheck`, `bun --cwd apps/cli test`, and `uv run --project apps/api pytest apps/api/tests`.
