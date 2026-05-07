import { existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import type { Toolchain } from "./runtime.js";

export interface WorkerStartOptions {
  runtimeDir: string;
  repoRoot: string;
  toolchain: Toolchain;
  apiUrl?: string;
  port?: number;
}

export interface WorkerState {
  pid: number;
  port: number;
  apiUrl: string;
  logsDir: string;
  external?: boolean;
}

export interface ApiEndpoint {
  port: number;
  apiUrl: string;
  reuseExisting: boolean;
}

export function startWorker(options: WorkerStartOptions): number {
  const port = options.port ?? 8000;
  const apiDir = join(options.runtimeDir, "runtime", "api");
  if (!existsSync(apiDir)) {
    throw new Error(`Codex-Mem API runtime was not found at ${apiDir}.`);
  }

  const logsDir = join(options.runtimeDir, "logs");
  mkdirSync(logsDir, { recursive: true });
  const out = openSync(join(logsDir, "api.log"), "a");
  const err = openSync(join(logsDir, "api.err.log"), "a");
  const sync = spawnSync(options.toolchain.uv, ["sync", "--project", apiDir], {
    cwd: apiDir,
    stdio: ["ignore", out, err],
    env: process.env,
  });
  if (sync.error) {
    throw sync.error;
  }
  if (sync.status !== 0) {
    throw new Error(`Codex-Mem API dependency sync failed. See ${join(logsDir, "api.err.log")}.`);
  }

  const uvicorn = process.platform === "win32"
    ? join(apiDir, ".venv", "Scripts", "uvicorn.exe")
    : join(apiDir, ".venv", "bin", "uvicorn");
  const child = spawn(uvicorn, ["app.main:app", "--host", "127.0.0.1", "--port", String(port)], {
    cwd: apiDir,
    detached: true,
    stdio: ["ignore", out, err],
    env: {
      ...process.env,
      CODEX_MEM_API_URL: options.apiUrl ?? `http://127.0.0.1:${port}`,
      CODEX_MEM_DATA_DIR: join(options.runtimeDir, "data"),
    },
  });
  child.unref();
  const pid = child.pid ?? 0;
  writeFileSync(join(options.runtimeDir, "worker.pid"), `${pid}\n`, "utf8");
  writeFileSync(join(options.runtimeDir, "worker.json"), `${JSON.stringify({ pid, port, apiUrl: options.apiUrl ?? `http://127.0.0.1:${port}`, logsDir }, null, 2)}\n`, "utf8");
  return pid;
}

export function readWorkerState(runtimeDir: string): WorkerState | null {
  const statePath = join(runtimeDir, "worker.json");
  if (existsSync(statePath)) {
    const state = JSON.parse(readFileSync(statePath, "utf8")) as WorkerState;
    return state.pid ? state : null;
  }
  const pidPath = join(runtimeDir, "worker.pid");
  if (!existsSync(pidPath)) {
    return null;
  }
  const pid = Number(readFileSync(pidPath, "utf8").trim());
  return Number.isFinite(pid) && pid > 0
    ? { pid, port: 8000, apiUrl: "http://127.0.0.1:8000", logsDir: join(runtimeDir, "logs") }
    : null;
}

export function writeWorkerState(runtimeDir: string, state: WorkerState): void {
  mkdirSync(runtimeDir, { recursive: true });
  writeFileSync(join(runtimeDir, "worker.json"), `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

export function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function stopWorker(runtimeDir: string): boolean {
  const state = readWorkerState(runtimeDir);
  if (!state || !processExists(state.pid)) {
    cleanupWorkerState(runtimeDir);
    return false;
  }
  process.kill(state.pid);
  cleanupWorkerState(runtimeDir);
  return true;
}

function cleanupWorkerState(runtimeDir: string): void {
  rmSync(join(runtimeDir, "worker.pid"), { force: true });
  rmSync(join(runtimeDir, "worker.json"), { force: true });
}

export async function waitForHealth(apiUrl: string, fetcher: typeof fetch = fetch, attempts = 20): Promise<void> {
  const base = apiUrl.replace(/\/$/, "");
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const health = await fetcher(`${base}/health`);
      const diagnostics = await fetcher(`${base}/memory/health/diagnostics`);
      if (health.ok && diagnostics.ok) {
        return;
      }
    } catch {
      // Retry until the worker has had time to bind its port.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Codex-Mem API did not pass health checks at ${base}.`);
}

export async function resolveApiEndpoint(preferredPort = 8000, fetcher: typeof fetch = fetch): Promise<ApiEndpoint> {
  const preferredUrl = `http://127.0.0.1:${preferredPort}`;
  if (await codexApiHealthy(preferredUrl, fetcher)) {
    return { port: preferredPort, apiUrl: preferredUrl, reuseExisting: true };
  }
  if (await canBindPort(preferredPort)) {
    return { port: preferredPort, apiUrl: preferredUrl, reuseExisting: false };
  }
  for (let port = preferredPort + 1; port < preferredPort + 50; port += 1) {
    if (await canBindPort(port)) {
      return { port, apiUrl: `http://127.0.0.1:${port}`, reuseExisting: false };
    }
  }
  throw new Error(`No free Codex-Mem API port found near ${preferredPort}.`);
}

async function codexApiHealthy(apiUrl: string, fetcher: typeof fetch): Promise<boolean> {
  try {
    await waitForHealth(apiUrl, fetcher, 1);
    return true;
  } catch {
    return false;
  }
}

function canBindPort(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.listen(port, "127.0.0.1", () => {
      server.close(() => resolve(true));
    });
  });
}
