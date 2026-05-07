import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(import.meta.dirname, "../..");
const tarball = resolve(repoRoot, process.argv[2] ?? "dist/release/codex-memory-1.0.0.tgz");
const tempRepo = mkdtempSync(join(tmpdir(), "codex-mem-npx-repo-"));
const tempHome = mkdtempSync(join(tmpdir(), "codex-mem-npx-home-"));
const env = { ...process.env, CODEX_MEM_HOME: tempHome };

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: tempRepo,
    env,
    shell: process.platform === "win32",
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function runCapture(command, args, input = undefined, extraEnv = {}) {
  const result = spawnSync(command, args, {
    cwd: tempRepo,
    env: { ...env, ...extraEnv },
    shell: process.platform === "win32",
    input,
    encoding: "utf8",
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    console.error(result.stdout);
    console.error(result.stderr);
    process.exit(result.status ?? 1);
  }
  return result.stdout;
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function frame(payload) {
  const body = JSON.stringify(payload);
  return `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n${body}`;
}

function readFrames(output) {
  const messages = [];
  let rest = output;
  while (rest.includes("\r\n\r\n")) {
    const boundary = rest.indexOf("\r\n\r\n");
    const header = rest.slice(0, boundary);
    const tail = rest.slice(boundary + 4);
    const match = header.match(/content-length:\s*(\d+)/i);
    if (!match) break;
    const length = Number(match[1]);
    const body = tail.slice(0, length);
    messages.push(JSON.parse(body));
    rest = tail.slice(length);
  }
  return messages;
}

try {
  run("npm", ["init", "-y"]);
  run("npx", ["--yes", "--package", tarball, "codex-memory", "install", "--yes"]);
  const configPath = join(tempRepo, ".codex", "mem.config.json");
  const marketplacePath = join(tempRepo, ".agents", "plugins", "marketplace.json");
  const pluginManifestPath = join(tempHome, "runtime", "plugin", ".codex-plugin", "plugin.json");
  assert(existsSync(configPath), "install did not create .codex/mem.config.json");
  assert(existsSync(pluginManifestPath), "install did not create user-level plugin manifest");
  assert(existsSync(marketplacePath), "install did not create marketplace config");

  const config = JSON.parse(readFileSync(configPath, "utf8"));
  const apiUrl = config.api?.url ?? "http://127.0.0.1:8000";
  const health = await fetch(`${apiUrl}/health`);
  assert(health.ok, "API health check failed");
  const diagnostics = await fetch(`${apiUrl}/memory/health/diagnostics`);
  assert(diagnostics.ok, "memory diagnostics health check failed");

  run("npx", ["--yes", "--package", tarball, "codex-memory", "remember", "--type", "fact", "--title", "Smoke memory", "--context", "npx install smoke wrote this memory."]);
  const queryOutput = runCapture("npx", ["--yes", "--package", tarball, "codex-memory", "query", "Smoke memory", "--limit", "1"]);
  assert(queryOutput.includes("Smoke memory"), "query did not return smoke memory");
  const activeHook = runCapture("npx", ["--yes", "--package", tarball, "codex-memory", "hook", "user-prompt"], JSON.stringify({ prompt: "Smoke memory" }));
  assert(activeHook.includes("hookSpecificOutput") || activeHook.includes("memory"), "active hook did not produce hook output");

  const mcpServer = join(tempHome, "runtime", "mcp-server", "dist", "server.js");
  const initialize = { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "smoke", version: "1.0.0" } } };
  const toolsList = { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} };
  const mcpOutput = runCapture("bun", [mcpServer], `${frame(initialize)}${frame(toolsList)}`, { CODEX_MEM_API_URL: apiUrl });
  const messages = readFrames(mcpOutput);
  const tools = messages.at(-1)?.result?.tools ?? [];
  assert(tools.some((tool) => tool.name === "query_memory"), "MCP tools list did not include query_memory");

  run("npx", ["--yes", "--package", tarball, "codex-memory", "status"]);
  run("npx", ["--yes", "--package", tarball, "codex-memory", "stop"]);
  const degradedHook = runCapture("npx", ["--yes", "--package", tarball, "codex-memory", "hook", "user-prompt"], JSON.stringify({ prompt: "Smoke memory after stop" }));
  assert(degradedHook.includes("degraded") || degradedHook.includes("unavailable"), "offline hook did not report degraded mode");
} finally {
  const pidPath = join(tempHome, "worker.pid");
  if (existsSync(pidPath)) {
    const pid = Number(readFileSync(pidPath, "utf8").trim());
    if (Number.isFinite(pid) && pid > 0) {
      try {
        process.kill(pid);
      } catch {
        // The worker may already have been stopped by the smoke command.
      }
    }
  }
  rmSync(tempRepo, { recursive: true, force: true });
  rmSync(tempHome, { recursive: true, force: true });
}
