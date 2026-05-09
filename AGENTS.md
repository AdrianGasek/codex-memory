# AGENTS.md example for Codex-Mem

Use this file as a practical memory-first operating guide for Codex.

Before implementing:

1. Query memory for relevant decisions, bugs, and patterns.
2. Use existing solutions when available.
3. Inspect the current code before changing it.
4. Store only validated, reusable knowledge after the fix works.

Memory types:

- `fact`
- `decision`
- `bug`
- `solution`
- `pattern`

Store memory when:

- a bug is identified and resolved
- a non-obvious solution is validated
- a recurring project pattern is confirmed
- an old assumption is proven wrong

Never store:

- secrets
- tokens
- credentials
- private personal data
- guesses
- temporary debugging notes

Project workflow:

1. Use `.codex/ROADMAP.md` as the implementation checklist.
2. Mark roadmap items `[x]` only after code exists and matching verification passes.
3. Keep roadmap changes tied to completed work.
4. After each completed code or documentation change, prepare a git commit with
   a clear imperative title and a body that explains what changed, why it
   changed, and what verification passed.

Memory is a decision aid. Current code is still the source of truth.
