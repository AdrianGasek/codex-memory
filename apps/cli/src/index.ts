#!/usr/bin/env bun
import { debugCommand } from "./commands/debug.js";
import { getCommand } from "./commands/get.js";
import { queryCommand } from "./commands/query.js";
import { rememberCommand } from "./commands/remember.js";
import { updateCommand } from "./commands/update.js";

const [, , command, ...args] = process.argv;

export async function runCommand(command: string | undefined, args: string[]): Promise<void> {
  switch (command) {
    case "remember":
    case "note":
    case "/note":
      await rememberCommand(args);
      return;
    case "update":
      await updateCommand(args);
      return;
    case "get":
      await getCommand(args);
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

async function main(): Promise<void> {
  await runCommand(command, args);
}

function printHelp(): void {
  console.log(`codex-mem

Commands:
  remember --type decision --title "..." --context "..." --resolution "..." --tag infra
  note --type fact --title "..."
  update <id> --title "..." --tag infra
  get <id>
  query "search terms" --profile short
  debug --query "current task" --profile deep

Environment:
  CODEX_MEM_API_URL=http://127.0.0.1:8000
`);
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
