import { parseOptions } from "./args.js";
import { ensureToolchain, userRuntimeDir } from "./runtime.js";
import {
  processExists,
  readWorkerState,
  resolveApiEndpoint,
  startWorker,
  stopWorker,
  waitForHealth,
  writeWorkerState,
} from "./worker.js";

export async function startCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const runtimeDir = userRuntimeDir();
  const preferredPort = Number(options.get("port")?.[0] ?? 8000);
  const existing = readWorkerState(runtimeDir);

  if (existing && processExists(existing.pid)) {
    console.log(
      `Codex-Mem worker already running: ${existing.apiUrl} pid=${existing.pid}`,
    );
    return;
  }

  const endpoint = await resolveApiEndpoint(preferredPort);
  if (endpoint.reuseExisting) {
    writeWorkerState(runtimeDir, {
      pid: 0,
      port: endpoint.port,
      apiUrl: endpoint.apiUrl,
      logsDir: `${runtimeDir}/logs`,
      external: true,
    });
    console.log(`Codex-Mem worker already available: ${endpoint.apiUrl}`);
    return;
  }

  const pid = startWorker({
    runtimeDir,
    repoRoot: process.cwd(),
    toolchain: ensureToolchain({ runtimeDir }),
    apiUrl: endpoint.apiUrl,
    port: endpoint.port,
  });
  if (!options.has("no-health")) {
    await waitForHealth(endpoint.apiUrl);
  }
  console.log(`Codex-Mem worker started: ${endpoint.apiUrl} pid=${pid}`);
}

export function stopCommand(): void {
  const stopped = stopWorker(userRuntimeDir());
  console.log(
    stopped ? "Codex-Mem worker stopped." : "Codex-Mem worker is not running.",
  );
}

export async function restartCommand(args: string[]): Promise<void> {
  stopWorker(userRuntimeDir());
  await startCommand(args);
}

export function statusCommand(): void {
  const runtimeDir = userRuntimeDir();
  const state = readWorkerState(runtimeDir);
  if (state?.external) {
    console.log(
      `Codex-Mem worker: running (external)\nAPI: ${state.apiUrl}\nLogs: ${state.logsDir}`,
    );
    return;
  }
  if (!state || !processExists(state.pid)) {
    console.log(`Codex-Mem worker: stopped\nRuntime: ${runtimeDir}`);
    return;
  }
  console.log(
    `Codex-Mem worker: running\nAPI: ${state.apiUrl}\nPID: ${state.pid}\nLogs: ${state.logsDir}`,
  );
}
