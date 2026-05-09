# Team Benefits

`codex-memory` is most useful when a project is long-lived and more than one
developer works with Codex across many sessions, branches, and fixes.

## Why It Helps

Long projects accumulate context that rarely fits into one prompt:

- why a framework, database, or deployment path was chosen
- which bugs already have known fixes
- which files are fragile or generated
- what conventions reviewers expect
- which commands verify a change safely

Without a shared project memory, each developer has to rediscover this context,
or paste it into every new Codex thread. `codex-memory` turns those durable
lessons into searchable local entries that can be injected back into future
sessions.

## Benefits For A Developer Team

- Faster onboarding: new contributors can query project decisions, known
  pitfalls, and setup notes before touching code.
- Fewer repeated mistakes: solved bugs become reusable memory instead of
  terminal scrollback.
- Better review consistency: conventions can be stored as `pattern` or
  `decision` entries and reused by Codex during implementation.
- Lower handoff cost: a developer can capture the fix, verification command,
  and affected area after a debugging session.
- More predictable Codex sessions: the agent starts with project-specific
  memory instead of generic assumptions.
- Local-first operation: memory stays in the developer environment by default,
  backed by SQLite under `~/.codex-mem`.

## Good Team Practices

Keep required rules in checked-in files such as `AGENTS.md`, README files, or
architecture docs. Use `codex-memory` for recall, search, debugging history, and
validated project knowledge.

Good entries are short and reusable:

```bash
codex-memory remember \
  --type decision \
  --title "Use SQLite as local memory source of truth" \
  --context "Storage architecture" \
  --resolution "Store canonical memory in SQLite; vector stores are indexes."
```

For team use, prefer entries that include:

- the type: `fact`, `decision`, `bug`, `solution`, or `pattern`
- the context in which the memory matters
- the validated fix or rule
- tags such as `frontend`, `release`, `windows`, or `database`

## What Not To Store

Do not store secrets, tokens, credentials, private personal data, or temporary
debugging guesses. Store only knowledge that another future session should be
able to trust.
