#!/usr/bin/env bun
import { debugCommand } from "./commands/debug.js";
import { queryCommand } from "./commands/query.js";
import { rememberCommand } from "./commands/remember.js";

const [, , command, ...args] = process.argv;

async function main(): Promise<void> {
  switch (command) {
    case "remember":
      await rememberCommand(args);
      return;
    case "query":
      await queryCommand(args);
      return;
    case "debug":
      await debugCommand(args);
      return;
    case "help":
    case undefined:
      printHelp();
      return;
    default:
      throw new Error(`Unknown command "${command}".`);
  }
}

function printHelp(): void {
  console.log(`codex-mem

Commands:
  remember --type decision --title "..." --context "..." --resolution "..." --tag infra
  query "search terms"
  debug --query "current task"

Environment:
  CODEX_MEM_API_URL=http://127.0.0.1:8000
`);
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
