import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";
import { spawnSync, type SpawnSyncReturns } from "node:child_process";

export interface Toolchain {
  bun: string;
  uv: string;
}

interface BootstrapOptions {
  runtimeDir?: string;
  env?: NodeJS.ProcessEnv;
  runner?: typeof spawnSync;
}

export function userRuntimeDir(env: NodeJS.ProcessEnv = process.env): string {
  return env.CODEX_MEM_HOME || join(homedir(), ".codex-mem");
}

export function ensureToolchain(options: BootstrapOptions = {}): Toolchain {
  const runtimeDir = options.runtimeDir ?? userRuntimeDir(options.env);
  const env = options.env ?? process.env;
  const runner = options.runner ?? spawnSync;
  mkdirSync(runtimeDir, { recursive: true });

  const bun = findCommand("bun", runner, env) ?? bootstrapBun(runtimeDir, runner, env);
  const uv = findCommand("uv", runner, env) ?? bootstrapUv(runtimeDir, runner, env);

  return { bun, uv };
}

function findCommand(command: string, runner: typeof spawnSync, env: NodeJS.ProcessEnv): string | null {
  const lookup = process.platform === "win32" ? "where.exe" : "command";
  const args = process.platform === "win32" ? [command] : ["-v", command];
  const result = runner(lookup, args, {
    env,
    encoding: "utf8",
    shell: process.platform !== "win32",
  });

  if (result.status !== 0 || !result.stdout) {
    return null;
  }
  return String(result.stdout).split(/\r?\n/).find(Boolean)?.trim() ?? null;
}

function bootstrapBun(runtimeDir: string, runner: typeof spawnSync, env: NodeJS.ProcessEnv): string {
  const toolsDir = join(runtimeDir, "tools", "bun");
  mkdirSync(toolsDir, { recursive: true });
  const npm = findCommand("npm", runner, env);
  if (!npm) {
    throw new Error("Bun is not installed and npm was not found, so Codex-Mem cannot bootstrap Bun.");
  }

  runOrThrow(runner(npm, ["install", "--prefix", toolsDir, "bun"], { env, stdio: "pipe", encoding: "utf8" }), "Could not bootstrap Bun with npm.");
  const bin = process.platform === "win32"
    ? join(toolsDir, "node_modules", ".bin", "bun.cmd")
    : join(toolsDir, "node_modules", ".bin", "bun");
  if (!existsSync(bin)) {
    throw new Error(`Bun bootstrap completed but ${bin} was not created.`);
  }
  return bin;
}

function bootstrapUv(runtimeDir: string, runner: typeof spawnSync, env: NodeJS.ProcessEnv): string {
  const uvDir = join(runtimeDir, "tools", "uv");
  mkdirSync(uvDir, { recursive: true });
  const installEnv = { ...env, UV_INSTALL_DIR: uvDir, UV_NO_MODIFY_PATH: "1", PATH: `${uvDir}${delimiter}${env.PATH ?? ""}` };

  const result = process.platform === "win32"
    ? runner("powershell", ["-ExecutionPolicy", "ByPass", "-NoProfile", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"], {
        env: installEnv,
        stdio: "pipe",
        encoding: "utf8",
      })
    : runner("sh", ["-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"], {
        env: installEnv,
        stdio: "pipe",
        encoding: "utf8",
      });

  runOrThrow(result, "Could not bootstrap uv with the standalone installer.");
  const bin = process.platform === "win32" ? join(uvDir, "uv.exe") : join(uvDir, "uv");
  if (!existsSync(bin)) {
    throw new Error(`uv bootstrap completed but ${bin} was not created.`);
  }
  return bin;
}

function runOrThrow(result: SpawnSyncReturns<string>, message: string): void {
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    const stderr = result.stderr ? ` ${String(result.stderr).trim()}` : "";
    throw new Error(`${message}${stderr}`);
  }
}
