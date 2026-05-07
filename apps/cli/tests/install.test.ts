import { afterEach, describe, expect, mock, test } from "bun:test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { installCommand, resolveConfigPath } from "../src/commands/install";

const originalCwd = process.cwd();
const originalLog = console.log;

afterEach(() => {
  process.chdir(originalCwd);
  console.log = originalLog;
});

describe("installCommand", () => {
  test("creates repo-local Codex-Mem config with local storage defaults", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    const logs: string[] = [];
    try {
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      const runtimeSource = fakeRuntimeSource(repo);
      process.chdir(repo);
      console.log = mock((message: string) => {
        logs.push(message);
      }) as unknown as typeof console.log;

      await installCommand(["--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);

      const config = JSON.parse(readFileSync(join(repo, ".codex", "mem.config.json"), "utf8"));
      expect(config).toMatchObject({
        project: repo.split(/[\\/]/).pop(),
        vector_backend: "local",
        api: {
          url: "http://127.0.0.1:8000",
          port: 8000,
        },
        storage: {
          data_dir: "data",
          db_path: "data/db/codex-mem.sqlite3",
        },
      });
      expect(config.security).toBeUndefined();
      expect(logs[0]).toContain(".codex");
    } finally {
      process.chdir(originalCwd);
      rmSync(repo, { recursive: true, force: true });
    }
  });

  test("preserves existing user config values", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    try {
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      const runtimeSource = fakeRuntimeSource(repo);
      await installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);

      const configPath = join(repo, ".codex", "mem.config.json");
      const config = JSON.parse(readFileSync(configPath, "utf8"));
      config.inject_limit = 9;
      config.storage.db_path = "custom/codex.sqlite3";
      writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");

      await installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);

      const updated = JSON.parse(readFileSync(configPath, "utf8"));
      expect(updated.inject_limit).toBe(9);
      expect(updated.storage.db_path).toBe("custom/codex.sqlite3");
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });

  test("installs runtime assets outside the repo", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    const runtimeHome = mkdtempSync(join(tmpdir(), "codex-mem-home-"));
    const originalHome = process.env.CODEX_MEM_HOME;
    try {
      process.env.CODEX_MEM_HOME = runtimeHome;
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      const runtimeSource = fakeRuntimeSource(repo);

      await installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);

      expect(existsSync(join(runtimeHome, "runtime", "api", "app", "main.py"))).toBe(true);
      expect(existsSync(join(runtimeHome, "runtime", "mcp-server", "dist", "server.js"))).toBe(true);
      expect(existsSync(join(runtimeHome, "runtime", "plugin", "scripts", "hook_memory.py"))).toBe(true);
      const mcp = JSON.parse(readFileSync(join(runtimeHome, "runtime", "plugin", ".mcp.json"), "utf8"));
      expect(mcp.mcpServers["codex-memory"].env.CODEX_MEM_API_URL).toBe("http://127.0.0.1:8000");
      expect(mcp.mcpServers["codex-memory"].args[0]).toContain(join("runtime", "mcp-server", "dist", "server.js"));
      expect(existsSync(join(repo, "runtime"))).toBe(false);
      const marketplace = JSON.parse(readFileSync(join(repo, ".agents", "plugins", "marketplace.json"), "utf8"));
      expect(marketplace.plugins[0].source.path).toBe(join(runtimeHome, "runtime", "plugin"));
    } finally {
      if (originalHome === undefined) {
        delete process.env.CODEX_MEM_HOME;
      } else {
        process.env.CODEX_MEM_HOME = originalHome;
      }
      rmSync(repo, { recursive: true, force: true });
      rmSync(runtimeHome, { recursive: true, force: true });
    }
  });

  test("rolls back marketplace when plugin health check fails", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    const runtimeHome = mkdtempSync(join(tmpdir(), "codex-mem-home-"));
    const originalHome = process.env.CODEX_MEM_HOME;
    try {
      process.env.CODEX_MEM_HOME = runtimeHome;
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      mkdirSync(join(repo, ".agents", "plugins"), { recursive: true });
      const originalMarketplace = "{\"plugins\":[{\"name\":\"other\"}]}\n";
      writeFileSync(join(repo, ".agents", "plugins", "marketplace.json"), originalMarketplace, "utf8");
      const runtimeSource = join(repo, "bad-runtime");
      mkdirSync(join(runtimeSource, "plugin"), { recursive: true });

      await expect(installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource])).rejects.toThrow("plugin install failed health check");

      expect(readFileSync(join(repo, ".agents", "plugins", "marketplace.json"), "utf8")).toBe(originalMarketplace);
    } finally {
      if (originalHome === undefined) {
        delete process.env.CODEX_MEM_HOME;
      } else {
        process.env.CODEX_MEM_HOME = originalHome;
      }
      rmSync(repo, { recursive: true, force: true });
      rmSync(runtimeHome, { recursive: true, force: true });
    }
  });

  test("dry run reports paths without writing config", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    const logs: string[] = [];
    try {
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

      await installCommand(["--cwd", repo, "--dry-run"]);

      expect(logs[0]).toContain("dry run");
      expect(existsSync(join(repo, ".codex", "mem.config.json"))).toBe(false);
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });

  test("dev toolkit mode prints repo-local workflow without writing config", async () => {
    const logs: string[] = [];
    console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

    await installCommand(["--dev-toolkit"]);

    expect(logs.join("\n")).toContain("bun install");
    expect(logs.join("\n")).toContain("uv sync --project apps/api");
  });

  test("migrates existing dev-toolkit data without overwriting runtime data", async () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-install-"));
    const runtimeHome = mkdtempSync(join(tmpdir(), "codex-mem-home-"));
    const originalHome = process.env.CODEX_MEM_HOME;
    try {
      process.env.CODEX_MEM_HOME = runtimeHome;
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      mkdirSync(join(repo, "data", "db"), { recursive: true });
      writeFileSync(join(repo, "data", "db", "codex-mem.sqlite3"), "repo-db", "utf8");
      const runtimeSource = fakeRuntimeSource(repo);

      await installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);

      expect(readFileSync(join(runtimeHome, "data", "db", "codex-mem.sqlite3"), "utf8")).toBe("repo-db");
      writeFileSync(join(runtimeHome, "data", "db", "codex-mem.sqlite3"), "runtime-db", "utf8");
      await installCommand(["--cwd", repo, "--yes", "--skip-bootstrap", "--no-start", "--runtime-source", runtimeSource]);
      expect(readFileSync(join(runtimeHome, "data", "db", "codex-mem.sqlite3"), "utf8")).toBe("runtime-db");
    } finally {
      if (originalHome === undefined) {
        delete process.env.CODEX_MEM_HOME;
      } else {
        process.env.CODEX_MEM_HOME = originalHome;
      }
      rmSync(repo, { recursive: true, force: true });
      rmSync(runtimeHome, { recursive: true, force: true });
    }
  });

  test("resolves installer storage paths for relative and absolute inputs", () => {
    const repo = "C:\\repo";
    expect(resolveConfigPath(repo, "data/db.sqlite3")).toBe("C:\\repo\\data\\db.sqlite3");
    expect(resolveConfigPath(repo, "C:\\data\\db.sqlite3")).toBe("C:\\data\\db.sqlite3");
  });
});

function fakeRuntimeSource(repo: string): string {
  const source = join(repo, "fake-runtime");
  mkdirSync(join(source, "api", "app"), { recursive: true });
  mkdirSync(join(source, "mcp-server", "dist"), { recursive: true });
  mkdirSync(join(source, "plugin", ".codex-plugin"), { recursive: true });
  mkdirSync(join(source, "plugin", "scripts"), { recursive: true });
  writeFileSync(join(source, "api", "app", "main.py"), "", "utf8");
  writeFileSync(join(source, "mcp-server", "dist", "server.js"), "", "utf8");
  writeFileSync(join(source, "plugin", ".codex-plugin", "plugin.json"), "{}", "utf8");
  writeFileSync(join(source, "plugin", "hooks.json"), "{}", "utf8");
  writeFileSync(join(source, "plugin", "scripts", "hook_memory.py"), "", "utf8");
  return source;
}
