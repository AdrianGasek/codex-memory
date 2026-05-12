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

- [x] Add `codex-memory optimize-context "task" --budget 6000 --strategy balanced`.
- [x] Support strategies: `minimal`, `balanced`, `deep`, `safety-first`.
- [x] Classify selected context as `must_include` or `nice_to_include`.
- [x] Report selected tokens, skipped tokens, saved-by-dedupe tokens, stale skips, and conflicts.
- [x] Add budget warnings when selected context is close to or over budget.
- [x] Add tests for each strategy.

## MVP 3: Memory Usage Stats

- [x] Add `codex-memory stats`.
- [x] Add `--project`, `--since`, and `--json` options.
- [x] Report memory calls by command.
- [x] Report total injected memories, average injected tokens, max injected tokens, and skipped due to budget.
- [x] Report most recalled files.
- [x] Report most used memory types.
- [x] Add `stats --impact` with memory-assisted sessions, boundary warnings, repeated bug reuse, and average context size.
- [x] Add API and CLI tests.

## MVP 4: Explain Why This Memory

- [x] Add `codex-memory explain-memory <memory-id>`.
- [x] Return ranking reason, matching query terms, file/path evidence, usage evidence, and conflict/staleness signals.
- [x] Add evidence arrays to `inject-preview` entries when available.
- [x] Add tests proving explanations are deterministic and redact secrets.

## MVP 5: Memory Health Check

- [x] Add `codex-memory health`.
- [x] Report DB, schema, vector backend, hooks, MCP, plugin config, and indexing state.
- [x] Report stale entries, duplicates, conflicting decisions, and largest memory chunks.
- [x] Recommend cleanup commands such as `prune`, `compact`, or `dedupe`.
- [x] Add JSON output for agents.
- [x] Add tests for healthy, warning, and error states.

## MVP 6: Memory Diff

- [x] Add `codex-memory diff <base-ref>`.
- [x] Detect new memory candidates from changed files and commits.
- [x] Detect outdated memory candidates after code changes.
- [x] Reuse existing handoff/git-diff capture logic where possible.
- [x] Add tests with fixture git histories.

## MVP 7: Memory Mode Status

- [x] Add `codex-memory status --memory-mode`.
- [x] Report whether memory is indexed, readable, writable, preview-enabled, and budget-limited.
- [x] Distinguish disabled, read-only, writable, and policy-blocked modes.
- [x] Add tests for config-driven status output.

## MVP 8: Dashboard TUI

- [x] Add `codex-memory dashboard`.
- [x] Include views for current project brain, recent recalls, token usage, risk map, stale memories, top recalled files, and current task scope.
- [x] Keep a non-interactive `--json` or `--summary` mode for agents and CI.
- [x] Add smoke tests for dashboard startup.

## MVP 9: Risk Map / Hotspot Graph

- [x] Add `codex-memory risk-map`.
- [x] Rank high-risk files by memory type, bug history, co-change frequency, and missing tests.
- [x] Include reasons for each hotspot.
- [x] Reuse risk-map output in `safe`, `plan`, and `review` flows.
- [x] Add tests for deterministic hotspot ordering.

## MVP 10: Session Audit

- [x] Add `codex-memory audit-session <session-id>`.
- [x] Show retrieved, injected, skipped, and potentially useful unused memories.
- [x] Warn when risky files were edited without relevant memory injection.
- [x] Warn when related memories existed but were not selected.
- [x] Add tests with recorded injection traces and file-change fixtures.

## MVP 11: Prune / Compact / Dedupe

- [x] Add `codex-memory prune --stale 90d`.
- [x] Add `codex-memory prune --low-hit-rate`.
- [x] Add `codex-memory compact --max-tokens 800`.
- [x] Add `codex-memory dedupe`.
- [x] Report removed, compacted, and superseded entries.
- [x] Require dry-run output before destructive cleanup unless `--yes` is passed.
- [x] Add tests proving protected/pinned memories are preserved.

## MVP 12: Pin / Never Inject / Promote

- [x] Add `codex-memory pin <memory-id>`.
- [x] Add `codex-memory never-inject <memory-id>`.
- [x] Add `codex-memory mark-stale <memory-id>`.
- [x] Add `codex-memory promote <memory-id> --to AGENTS.md`.
- [x] Suggest promotion when a memory is frequently used and looks like a stable project rule.
- [x] Add tests for pinned, blocked, stale, and promoted memory behavior.

## Documentation And Release

- [x] Update README with `inject-preview`, budget reports, and JSON examples.
- [x] Add examples for agents and humans.
- [x] Add changelog entry for each shipped MVP.
- [x] Run full verification before release: `bun run typecheck`, `bun --cwd apps/cli test`, and `uv run --project apps/api pytest apps/api/tests`.
