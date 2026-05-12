#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { debugCommand } from "./commands/debug.js";
import { devCommand } from "./commands/dev.js";
import { doctorCommand } from "./commands/doctor.js";
import { explainMemoryCommand } from "./commands/explainMemory.js";
import {
  auditSessionCommand,
  cleanupCommand,
  dashboardCommand,
  diffCommand,
  markStaleCommand,
  memoryModeStatusCommand,
  neverInjectCommand,
  pinCommand,
  promoteCommand,
  riskMapCommand,
} from "./commands/extraCommands.js";
import { getCommand } from "./commands/get.js";
import { healthCommand } from "./commands/health.js";
import { hookCommand } from "./commands/hook.js";
import { injectPreviewCommand } from "./commands/injectPreview.js";
import { installCommand } from "./commands/install.js";
import { optimizeContextCommand } from "./commands/optimizeContext.js";
import { queryCommand } from "./commands/query.js";
import { rememberCommand } from "./commands/remember.js";
import { statsCommand } from "./commands/stats.js";
import { uninstallCommand } from "./commands/uninstall.js";
import { updateCommand } from "./commands/update.js";
import { upgradeCommand } from "./commands/upgrade.js";
import {
  restartCommand,
  startCommand,
  statusCommand,
  stopCommand,
} from "./commands/workerCommands.js";

const [, , command, ...args] = process.argv;

export async function runCommand(
  command: string | undefined,
  args: string[],
): Promise<void> {
  switch (command) {
    case "--version":
    case "-v":
    case "version":
      printVersion();
      return;
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
    case "explain-memory":
      await explainMemoryCommand(args);
      return;
    case "query":
      await queryCommand(args);
      return;
    case "debug":
      await debugCommand(args);
      return;
    case "stats":
      await statsCommand(args);
      return;
    case "diff":
      await diffCommand(args);
      return;
    case "dashboard":
      await dashboardCommand(args);
      return;
    case "risk-map":
      await riskMapCommand();
      return;
    case "audit-session":
      await auditSessionCommand(args);
      return;
    case "prune":
    case "compact":
    case "dedupe":
      await cleanupCommand(command, args);
      return;
    case "pin":
      await pinCommand(args);
      return;
    case "never-inject":
      await neverInjectCommand(args);
      return;
    case "mark-stale":
      await markStaleCommand(args);
      return;
    case "promote":
      await promoteCommand(args);
      return;
    case "inject-preview":
    case "preview":
      await injectPreviewCommand(args);
      return;
    case "optimize-context":
      await optimizeContextCommand(args);
      return;
    case "doctor":
      await doctorCommand();
      return;
    case "health":
      await healthCommand(args);
      return;
    case "dev":
      devCommand(args);
      return;
    case "install":
      await installCommand(args);
      return;
    case "hook":
      hookCommand(args);
      return;
    case "start":
      await startCommand(args);
      return;
    case "stop":
      stopCommand();
      return;
    case "restart":
      await restartCommand(args);
      return;
    case "status":
      if (args.includes("--memory-mode")) {
        await memoryModeStatusCommand();
        return;
      }
      statusCommand();
      return;
    case "uninstall":
      uninstallCommand(args);
      return;
    case "upgrade":
      upgradeCommand();
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
  console.log(`codex-memory

Commands:
  remember --type decision --title "..." --context "..." --resolution "..." --tag infra
  note --type fact --title "..."
  update <id> --title "..." --tag infra
  get <id>
  explain-memory <id>
  query "search terms" --profile short
  inject-preview "current task" --budget 4000 --json
  optimize-context "current task" --budget 6000 --strategy balanced
  stats --project current --since 7d --json
  diff <base-ref>
  dashboard --summary
  risk-map
  audit-session <session-id>
  prune --stale 90d | compact --max-tokens 800 | dedupe
  pin <id> | never-inject <id> | mark-stale <id> | promote <id> --to AGENTS.md
  debug --query "current task" --profile deep
  dev doctor
  doctor
  health --json
  install --yes
  hook <session-start|user-prompt|stop|post-tool-use>
  status | start | stop | restart
  uninstall
  upgrade

Environment:
  CODEX_MEM_API_URL=http://127.0.0.1:8000
`);
}

function printVersion(): void {
  const packageJson = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  );
  console.log(String(packageJson.version));
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  });
}
