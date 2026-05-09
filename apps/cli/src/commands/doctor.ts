import { existsSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { userRuntimeDir } from "./runtime.js";
import { readWorkerState } from "./worker.js";

export async function doctorCommand(): Promise<void> {
  const runtimeDir = userRuntimeDir();
  const state = readWorkerState(runtimeDir);
  const apiUrl = state?.apiUrl ?? "http://127.0.0.1:8000";
  const dbDir = join(runtimeDir, "data", "db");
  const dbPath = join(dbDir, "codex-mem.sqlite3");
  const mcpServerPath = join(
    runtimeDir,
    "runtime",
    "mcp-server",
    "dist",
    "server.js",
  );
  const pluginConfigPath = join(
    runtimeDir,
    "runtime",
    "plugin",
    ".codex-plugin",
    "plugin.json",
  );
  const hooksPath = join(runtimeDir, "runtime", "plugin", "hooks.json");

  console.log(`Node: ${commandStatus("node", ["--version"])}`);
  console.log(`npm: ${commandStatus("npm", ["--version"])}`);
  console.log(`Bun: ${commandStatus("bun", ["--version"])}`);
  console.log(`uv: ${commandStatus("uv", ["--version"])}`);
  console.log(`Runtime: ${runtimeDir}`);
  console.log(`API URL: ${apiUrl}`);
  console.log(`API: ${await httpStatus(`${apiUrl}/health`)}`);
  console.log(`DB directory: ${pathStatus(dbDir)}`);
  console.log(`DB file: ${pathStatus(dbPath)}`);
  console.log(`MCP server: ${pathStatus(mcpServerPath)}`);
  console.log(`Plugin config: ${pathStatus(pluginConfigPath)}`);
  console.log(`Hooks: ${pathStatus(hooksPath)}`);
  console.log(`Port: ${state?.port ?? 8000}`);
  if (process.platform === "win32") {
    console.log(
      "Windows note: use npx.cmd if PowerShell cannot resolve npx, and keep the runtime path outside synced folders with restrictive permissions.",
    );
  }
}

function commandStatus(command: string, args: string[]): string {
  const result = spawnSync(command, args, {
    shell: process.platform === "win32",
    encoding: "utf8",
  });
  return result.status === 0 ? String(result.stdout).trim() || "ok" : "missing";
}

function pathStatus(path: string): string {
  return existsSync(path) ? `ok (${path})` : `missing (${path})`;
}

async function httpStatus(url: string): Promise<string> {
  try {
    const response = await fetch(url);
    return response.ok ? "ok" : `error ${response.status}`;
  } catch {
    return "offline";
  }
}
