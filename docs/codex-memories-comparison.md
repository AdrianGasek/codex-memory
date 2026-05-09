# codex-memory And Codex Memories

OpenAI's official [Codex memories](https://developers.openai.com/codex/memories)
and `codex-memory` solve related problems, but they sit at different layers.

Codex memories are a built-in Codex feature for carrying useful context from
earlier threads into future work. The official docs say memories are off by
default, can remember stable preferences, workflows, tech stacks, project
conventions, and known pitfalls, and should be treated as a helpful recall layer
rather than the only source for required team rules.

`codex-memory` is a project-local package that stores explicit, typed memory in
SQLite, exposes CLI and MCP tools, and wires Codex hooks so project knowledge can
be searched and injected in a repeatable way.

## Quick Comparison

| Area            | Codex memories                                                   | `codex-memory`                                                           |
| --------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Source          | Built into Codex                                                 | npm package installed per project                                        |
| Enablement      | Enabled in Codex settings or config                              | `npx codex-memory install`                                               |
| Availability    | Official docs note launch limits for EEA, UK, and Switzerland    | Runs locally wherever the package and runtime can run                    |
| Storage         | Codex home, under generated memory files                         | `~/.codex-mem` SQLite runtime by default                                 |
| Control surface | Codex settings, `/memories`, config keys                         | CLI commands, MCP tools, hooks, project config                           |
| Shape of memory | Generated from eligible threads                                  | Explicit typed entries: `fact`, `decision`, `bug`, `solution`, `pattern` |
| Best for        | Personal recall across Codex usage                               | Project-specific operational knowledge and team workflows                |
| Required rules  | Official docs recommend checked-in docs for must-follow guidance | Works alongside `AGENTS.md`, README, and architecture docs               |

## When To Use Codex Memories

Use Codex memories for personal or environment-level recall:

- recurring personal preferences
- stable workflow habits
- general tech stack familiarity
- context from prior Codex threads

Codex memories are especially useful when you want Codex itself to manage memory
generation in the background.

## When To Use codex-memory

Use `codex-memory` when the knowledge belongs to the project:

- a bug and its verified fix
- a release checklist
- a database or API design decision
- a Windows install workaround
- a repo-specific testing pattern
- a convention that multiple developers should reuse

Because entries are explicit and typed, `codex-memory` is easier to audit,
query, and reference in docs or team workflows.

## How They Work Together

They are complementary:

1. Put non-negotiable rules in `AGENTS.md` or checked-in docs.
2. Use Codex memories for broad personal recall.
3. Use `codex-memory` for validated, project-local knowledge that should survive
   across sessions and be discoverable by a team.

That separation keeps important rules visible in git while still letting Codex
and `codex-memory` reduce repeated context-setting.

## Official References

- [OpenAI Codex memories](https://developers.openai.com/codex/memories)
- [OpenAI Codex rules and AGENTS.md docs](https://developers.openai.com/codex/rules)
- [OpenAI Codex MCP docs](https://developers.openai.com/codex/mcp)
