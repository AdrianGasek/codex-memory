import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { userRuntimeDir } from "./runtime.js";

export function hookCommand(args: string[]): void {
  const [event] = args;
  if (!event) {
    throw new Error("Missing hook event. Use codex-memory hook <event>.");
  }

  const script = hookScriptPath();
  const result = spawnSync("python", [script, event], {
    stdio: "inherit",
    env: process.env,
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function hookScriptPath(): string {
  const installed = join(userRuntimeDir(), "runtime", "plugin", "scripts", "hook_memory.py");
  if (existsSync(installed)) {
    return installed;
  }
  const dev = resolve(fileURLToPath(new URL("../../../../plugins/codex-mem/scripts/hook_memory.py", import.meta.url)));
  if (existsSync(dev)) {
    return dev;
  }
  throw new Error("Codex-Mem hook runner was not found. Run codex-memory install first.");
}
