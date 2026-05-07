import { existsSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { userRuntimeDir } from "./runtime.js";
import { readWorkerState } from "./worker.js";

export async function doctorCommand(): Promise<void> {
  const runtimeDir = userRuntimeDir();
  const state = readWorkerState(runtimeDir);
  const apiUrl = state?.apiUrl ?? "http://127.0.0.1:8000";

  console.log(`Node: ${commandStatus("node", ["--version"])}`);
  console.log(`npm: ${commandStatus("npm", ["--version"])}`);
  console.log(`Bun: ${commandStatus("bun", ["--version"])}`);
  console.log(`uv: ${commandStatus("uv", ["--version"])}`);
  console.log(`API: ${await httpStatus(`${apiUrl}/health`)}`);
  console.log(`DB: ${existsSync(join(runtimeDir, "data", "db")) ? "ok" : "missing"}`);
  console.log(`MCP: ${existsSync(join(runtimeDir, "runtime", "mcp-server", "dist", "server.js")) ? "ok" : "missing"}`);
  console.log(`Plugin config: ${existsSync(join(runtimeDir, "runtime", "plugin", ".codex-plugin", "plugin.json")) ? "ok" : "missing"}`);
  console.log(`Hooks: ${existsSync(join(runtimeDir, "runtime", "plugin", "hooks.json")) ? "ok" : "missing"}`);
  console.log(`Port: ${state?.port ?? 8000}`);
}

function commandStatus(command: string, args: string[]): string {
  const result = spawnSync(command, args, { shell: process.platform === "win32", encoding: "utf8" });
  return result.status === 0 ? String(result.stdout).trim() || "ok" : "missing";
}

async function httpStatus(url: string): Promise<string> {
  try {
    const response = await fetch(url);
    return response.ok ? "ok" : `error ${response.status}`;
  } catch {
    return "offline";
  }
}
