# AGENTS.md

## Overview

This project implements a persistent memory system for AI agents operating in Codex environments.
Its purpose is to enable agents to **learn across sessions**, **reuse past solutions**, and **avoid repeated mistakes**.

The system introduces a structured memory layer that sits between the agent and its execution context:

```
capture → normalize → store → retrieve → rank → inject
```

Agents interacting with this system are expected to use memory as a **first-class capability**, not as an optional feature.

---

## Core Responsibilities of the Agent

When operating in this repository, the agent must:

1. **Consult memory before acting**

   * Always query memory for relevant past knowledge before generating solutions
   * Prefer existing solutions over generating new ones

2. **Capture meaningful knowledge**

   * Store new insights, fixes, and patterns
   * Avoid storing trivial or redundant information

3. **Continuously improve behavior**

   * Learn from mistakes
   * Reinforce successful approaches
   * Update outdated or incorrect memory

4. **Operate within context limits**

   * Inject only relevant memory into prompts
   * Respect token budgets and prioritize high-signal entries

5. **Track project progress**

   * Use `.codex/ROADMAP.md` as the canonical implementation checklist
   * Mark items `[x]` only after code exists and the matching verification passes
   * Keep roadmap changes tied to concrete, completed features

---

## Memory Types

The system organizes knowledge into structured categories:

* **fact** — objective information about the system
* **decision** — architectural or implementation choices
* **bug** — identified issues or failures
* **solution** — validated fixes or working implementations
* **pattern** — reusable approaches or best practices

Each memory entry should be concise, structured, and actionable.

---

## When to Query Memory

The agent must query memory:

* before implementing new functionality
* when encountering an error or unexpected behavior
* when working in unfamiliar parts of the codebase
* when making architectural decisions

Failure to query memory leads to redundant work and repeated mistakes.

---

## When to Store Memory

The agent should store memory when:

* a bug is identified and resolved
* a non-obvious solution is discovered
* a recurring pattern is recognized
* an assumption is proven wrong
* a performance or reliability improvement is implemented

Do NOT store:

* trivial outputs
* temporary debugging steps
* incomplete or unverified ideas

---

## Memory Quality Rules

All stored memory must follow these principles:

* **Specific** — clearly describe the context and outcome
* **Actionable** — useful for future decisions
* **Concise** — minimal but sufficient detail
* **Non-duplicative** — avoid redundancy
* **Validated** — only store confirmed knowledge

---

## Retrieval Behavior

When retrieving memory, the agent must:

* prioritize relevance over quantity
* prefer high-confidence entries
* combine multiple related entries if needed
* discard outdated or conflicting knowledge

Memory is a **decision aid**, not a source of truth.

---

## Conflict Handling

If multiple memory entries conflict:

1. Prefer the most recent validated entry
2. Cross-check against current codebase state
3. If uncertainty remains, ask for clarification instead of guessing

---

## Interaction with Codex

The agent operates through Codex using an MCP-compatible interface.

Available operations include:

* `store_memory` — persist structured knowledge
* `query_memory` — retrieve relevant entries
* `delete_memory` — remove invalid or outdated entries

The agent must treat these operations as part of its standard workflow.

---

## Context Injection Strategy

Memory should be injected into prompts:

* only when relevant to the current task
* in compressed form when possible
* with priority given to:

  * past solutions
  * known bugs
  * critical patterns

Avoid overloading the prompt with low-value memory.

---

## Error Handling and Learning

When an error occurs:

1. Analyze the root cause
2. Check if similar issues exist in memory
3. Apply known solutions if available
4. If resolved, store the new knowledge

Repeated errors indicate failure to use memory effectively.

---

## Performance Considerations

* Limit memory retrieval to top-ranked entries
* Use summarization when memory is too large
* Avoid unnecessary writes to memory storage
* Optimize for signal-to-noise ratio

---

## Security and Safety

The agent must never store:

* secrets (API keys, tokens, credentials)
* personally identifiable information (PII)
* sensitive system data

All memory should be safe for reuse and inspection.

---

## Expected Behavior

A correctly operating agent will:

* become more efficient over time
* reduce duplicate work
* avoid repeating known mistakes
* build a growing knowledge base
* make increasingly informed decisions

Failure to improve over time indicates improper memory usage.

---

## Summary

This system transforms the agent from a stateless executor into a **learning system**.

Memory is not optional.

Memory is the system.
