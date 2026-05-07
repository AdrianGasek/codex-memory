---
name: mem-search
description: Search Codex-Mem project memory before making implementation decisions or when debugging repeated issues.
---

Before implementing or debugging, query Codex-Mem through the `query_memory` MCP tool with a concise description of the task.

Use the returned memory as a decision aid. Trust current repository state over stored memory when they conflict.

Store durable findings with `store_memory` only when they are validated, reusable, and non-trivial. Never store secrets, credentials, PII, transient logs, or guesses.
