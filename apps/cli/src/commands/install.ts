import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
import {
  basename,
  dirname,
  isAbsolute,
  join,
  parse,
  relative,
  resolve,
} from "node:path";
import { parseOptions } from "./args.js";
import { ensureToolchain, userRuntimeDir } from "./runtime.js";
import {
  resolveApiEndpoint,
  startWorker,
  waitForHealth,
  writeWorkerState,
} from "./worker.js";

interface MemConfig {
  project?: string;
  inject_limit?: number;
  token_budget?: number;
  vector_backend?: string;
  storage?: {
    data_dir?: string;
    db_path?: string;
  };
  api?: {
    url?: string;
    port?: number;
  };
  embeddings?: {
    provider?: string;
    model?: string;
  };
  summarization?: {
    provider?: string;
    model?: string;
  };
  capture?: {
    mode?: string;
    ignore_paths?: string[];
  };
  debug?: {
    verbose?: boolean;
  };
}

export async function installCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  if (options.has("dev-toolkit")) {
    console.log("Developer Toolkit setup:");
    console.log("  bun install");
    console.log("  uv sync --project apps/api");
    console.log("  bun run api:dev");
    console.log("  bun run mcp:dev");
    console.log("  bun run cli:test");
    console.log("  bun run api:test");
    return;
  }
  const cwd = resolve(options.get("cwd")?.[0] ?? process.cwd());
  const repoRoot = findRepoRoot(cwd);
  const codexDir = join(repoRoot, ".codex");
  const configPath = join(codexDir, "mem.config.json");
  const existing = readExistingConfig(configPath);
  const config = mergeConfig(defaultConfig(repoRoot), existing);
  const runtimeDir = userRuntimeDir();
  const runtimeSource = resolve(
    options.get("runtime-source")?.[0] ??
      fileURLToPath(new URL("../../runtime", import.meta.url)),
  );
  if (options.has("dry-run")) {
    console.log(
      `Codex-Mem install dry run: repo=${repoRoot} runtime=${runtimeDir} config=${configPath} source=${runtimeSource}`,
    );
    return;
  }

  mkdirSync(codexDir, { recursive: true });
  mkdirSync(runtimeDir, { recursive: true });
  const toolchain = options.has("skip-bootstrap")
    ? { bun: "bun", uv: "uv" }
    : ensureToolchain({ runtimeDir });
  const marketplaceBackup = backupMarketplace(repoRoot);
  installRuntimeAssets(runtimeSource, join(runtimeDir, "runtime"));
  migrateDevToolkitData(repoRoot, runtimeDir);
  let apiUrl = config.api?.url ?? "http://127.0.0.1:8000";
  if (!options.has("no-start")) {
    const endpoint = await resolveApiEndpoint(8000);
    apiUrl = endpoint.apiUrl;
    config.api = { url: endpoint.apiUrl, port: endpoint.port };
    if (endpoint.reuseExisting) {
      writeWorkerState(runtimeDir, {
        pid: 0,
        port: endpoint.port,
        apiUrl: endpoint.apiUrl,
        logsDir: join(runtimeDir, "logs"),
        external: true,
      });
    } else {
      startWorker({
        runtimeDir,
        repoRoot,
        toolchain,
        apiUrl: endpoint.apiUrl,
        port: endpoint.port,
      });
    }
    await waitForHealth(endpoint.apiUrl);
  }
  try {
    writeMcpConfig(runtimeDir, toolchain.bun, apiUrl);
    updateMarketplace(repoRoot, join(runtimeDir, "runtime", "plugin"));
    validatePluginInstall(runtimeDir);
  } catch (error) {
    restoreMarketplace(repoRoot, marketplaceBackup);
    throw error;
  }
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");

  console.log(
    `Codex-Mem config: ${relative(process.cwd(), configPath) || configPath}`,
  );
}

export function findRepoRoot(start: string): string {
  let current = resolve(start);
  const root = parse(current).root;

  while (true) {
    if (
      existsSync(join(current, ".git")) ||
      existsSync(join(current, "package.json"))
    ) {
      return current;
    }
    if (current === root) {
      return resolve(start);
    }
    current = dirname(current);
  }
}

function defaultConfig(repoRoot: string): Required<MemConfig> {
  return {
    project: basename(repoRoot),
    inject_limit: 5,
    token_budget: 1200,
    vector_backend: "local",
    storage: {
      data_dir: "data",
      db_path: "data/db/codex-mem.sqlite3",
    },
    api: {
      url: "http://127.0.0.1:8000",
      port: 8000,
    },
    embeddings: {
      provider: "local",
      model: "local-hash",
    },
    summarization: {
      provider: "local",
      model: "extractive",
    },
    capture: {
      mode: "active",
      ignore_paths: ["data/db", "data/vectors"],
    },
    debug: {
      verbose: false,
    },
  };
}

function readExistingConfig(path: string): MemConfig {
  if (!existsSync(path)) {
    return {};
  }
  const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${path} must contain a JSON object.`);
  }
  return parsed as MemConfig;
}

function mergeConfig(
  defaults: Required<MemConfig>,
  existing: MemConfig,
): MemConfig {
  return {
    ...defaults,
    ...existing,
    storage: { ...defaults.storage, ...existing.storage },
    api: { ...defaults.api, ...existing.api },
    embeddings: { ...defaults.embeddings, ...existing.embeddings },
    summarization: { ...defaults.summarization, ...existing.summarization },
    capture: { ...defaults.capture, ...existing.capture },
    debug: { ...defaults.debug, ...existing.debug },
  };
}

export function resolveConfigPath(
  repoRoot: string,
  configuredPath: string,
): string {
  return isAbsolute(configuredPath)
    ? configuredPath
    : join(repoRoot, configuredPath);
}

export function installRuntimeAssets(
  sourceDir: string,
  targetDir: string,
): void {
  if (!existsSync(sourceDir)) {
    throw new Error(
      `Codex-Mem runtime assets were not found at ${sourceDir}. Run the package build before installing.`,
    );
  }
  rmSync(targetDir, { recursive: true, force: true });
  mkdirSync(targetDir, { recursive: true });
  cpSync(sourceDir, targetDir, { recursive: true });
}

export function writeMcpConfig(
  runtimeDir: string,
  bunCommand: string,
  apiUrl: string,
): void {
  const mcpPath = join(runtimeDir, "runtime", "plugin", ".mcp.json");
  const config = {
    mcpServers: {
      "codex-memory": {
        command: bunCommand,
        args: [join(runtimeDir, "runtime", "mcp-server", "dist", "server.js")],
        env: {
          CODEX_MEM_API_URL: apiUrl,
        },
      },
    },
  };
  writeFileSync(mcpPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");
}

export function updateMarketplace(repoRoot: string, pluginPath: string): void {
  const marketplacePath = join(
    repoRoot,
    ".agents",
    "plugins",
    "marketplace.json",
  );
  mkdirSync(dirname(marketplacePath), { recursive: true });
  const marketplace = readMarketplace(marketplacePath);
  const plugin = {
    name: "codex-memory",
    source: {
      source: "local",
      path: pluginPath,
    },
    policy: {
      installation: "AVAILABLE",
      authentication: "ON_INSTALL",
    },
    category: "Productivity",
  };
  const plugins = Array.isArray(marketplace.plugins) ? marketplace.plugins : [];
  const index = plugins.findIndex(
    (entry) =>
      entry &&
      typeof entry === "object" &&
      "name" in entry &&
      ["codex-memory", "codex-mem"].includes(String(entry.name)),
  );
  if (index >= 0) {
    plugins[index] = plugin;
  } else {
    plugins.push(plugin);
  }
  marketplace.plugins = plugins;
  marketplace.name = marketplace.name ?? "codex-memory-local";
  marketplace.interface = marketplace.interface ?? {
    displayName: "Codex-Memory Local",
  };
  writeFileSync(
    marketplacePath,
    `${JSON.stringify(marketplace, null, 2)}\n`,
    "utf8",
  );
}

export function backupMarketplace(repoRoot: string): string | null {
  const marketplacePath = join(
    repoRoot,
    ".agents",
    "plugins",
    "marketplace.json",
  );
  return existsSync(marketplacePath)
    ? readFileSync(marketplacePath, "utf8")
    : null;
}

export function restoreMarketplace(
  repoRoot: string,
  backup: string | null,
): void {
  const marketplacePath = join(
    repoRoot,
    ".agents",
    "plugins",
    "marketplace.json",
  );
  if (backup === null) {
    rmSync(marketplacePath, { force: true });
    return;
  }
  mkdirSync(dirname(marketplacePath), { recursive: true });
  writeFileSync(marketplacePath, backup, "utf8");
}

export function validatePluginInstall(runtimeDir: string): void {
  const pluginDir = join(runtimeDir, "runtime", "plugin");
  const required = [
    join(pluginDir, ".codex-plugin", "plugin.json"),
    join(pluginDir, ".mcp.json"),
    join(pluginDir, "hooks.json"),
    join(pluginDir, "scripts", "hook_memory.py"),
  ];
  for (const path of required) {
    if (!existsSync(path)) {
      throw new Error(
        `Codex-Mem plugin install failed health check: missing ${path}.`,
      );
    }
  }
}

export function migrateDevToolkitData(
  repoRoot: string,
  runtimeDir: string,
): void {
  const migrations = [
    ["data/db", "data/db"],
    ["data/vectors", "data/vectors"],
  ] as const;
  for (const [sourceRelative, targetRelative] of migrations) {
    const source = join(repoRoot, sourceRelative);
    const target = join(runtimeDir, targetRelative);
    if (existsSync(source) && !existsSync(target)) {
      mkdirSync(dirname(target), { recursive: true });
      cpSync(source, target, { recursive: true });
    }
  }
}

function readMarketplace(
  path: string,
): Record<string, unknown> & { plugins?: Array<Record<string, unknown>> } {
  if (!existsSync(path)) {
    return {};
  }
  const parsed = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${path} must contain a JSON object.`);
  }
  return parsed as Record<string, unknown> & {
    plugins?: Array<Record<string, unknown>>;
  };
}
