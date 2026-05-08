# Philosophy

Codex-Mem exists because useful agent work depends on history. Good project memory helps Codex avoid repeated mistakes, reuse known fixes, and carry decisions across sessions.

## Core Principle

```text
Do not guess.
Do not repeat work.
Do not ignore history.
```

Every action should be grounded in:

- current context
- existing code
- stored memory

## Working Model

Before acting:

1. Understand the task.
2. Identify unknowns.
3. Check memory.
4. Inspect the codebase.
5. Decide the safest path.

When solving:

- prefer known solutions over new ones
- adapt instead of reinventing
- make small, correct changes
- verify before storing new memory

## Memory Discipline

Only store knowledge that is:

- validated
- reusable
- non-trivial
- specific

Do not store guesses, temporary debugging steps, secrets, credentials, tokens, or private personal data.

## Conflict Resolution

When memory conflicts with the current repo:

1. Trust current code first.
2. Prefer recent validated memory over old memory.
3. Verify before acting.
4. Ask when the conflict remains unresolved.

Memory is a decision aid, not a substitute for reading the code.
