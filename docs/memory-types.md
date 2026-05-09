# Memory Types

`codex-memory remember` stores durable project knowledge. Prefer concise entries
that future Codex sessions can reuse.

## fact

Use facts for stable project information.

```bash
codex-memory remember \
  --type fact \
  --title "Frontend uses Next.js" \
  --context "Application stack" \
  --resolution "Use Next.js conventions for routing and build commands." \
  --tag frontend
```

Query:

```text
$ codex-memory query "frontend stack"
[fact] Frontend uses Next.js
Use Next.js conventions for routing and build commands.
```

## decision

Use decisions for tradeoffs the team has already made.

```bash
codex-memory remember \
  --type decision \
  --title "Use SQLite as local source of truth" \
  --context "Memory storage backend" \
  --resolution "Keep canonical memory in SQLite; vector stores are indexes." \
  --tag storage
```

Query:

```text
$ codex-memory query "memory storage"
[decision] Use SQLite as local source of truth
Keep canonical memory in SQLite; vector stores are indexes.
```

## bug

Use bugs for known failures and the confirmed fix.

```bash
codex-memory remember \
  --type bug \
  --title "Windows shell cannot resolve npx" \
  --context "PowerShell install path" \
  --resolution "Run npx.cmd codex-memory install, then codex-memory doctor." \
  --tag windows
```

Query:

```text
$ codex-memory query "PowerShell npx"
[bug] Windows shell cannot resolve npx
Run npx.cmd codex-memory install, then codex-memory doctor.
```

## solution

Use solutions for reusable implementation recipes.

```bash
codex-memory remember \
  --type solution \
  --title "Verify package before npm publish" \
  --context "Release workflow" \
  --resolution "Run release check, smoke.sh, and pack:smoke before publish." \
  --tag release
```

Query:

```text
$ codex-memory query "npm publish checks"
[solution] Verify package before npm publish
Run release check, smoke.sh, and pack:smoke before publish.
```

## pattern

Use patterns for recurring coding or operating conventions.

```bash
codex-memory remember \
  --type pattern \
  --title "Keep API routes thin" \
  --context "Backend architecture" \
  --resolution "Routes validate input and call storage/services for behavior." \
  --tag backend
```

Query:

```text
$ codex-memory query "backend route convention"
[pattern] Keep API routes thin
Routes validate input and call storage/services for behavior.
```
