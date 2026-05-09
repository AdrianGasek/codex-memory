import { afterEach, describe, expect, mock, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { doctorCommand } from "../src/commands/doctor";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
const originalHome = process.env.CODEX_MEM_HOME;

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  if (originalHome === undefined) {
    delete process.env.CODEX_MEM_HOME;
  } else {
    process.env.CODEX_MEM_HOME = originalHome;
  }
});

describe("doctorCommand", () => {
  test("prints explicit runtime, API, DB, MCP, plugin, and hook diagnostics", async () => {
    const runtime = mkdtempSync(join(tmpdir(), "codex-mem-doctor-"));
    const logs: string[] = [];
    try {
      process.env.CODEX_MEM_HOME = runtime;
      mkdirSync(join(runtime, "data", "db"), { recursive: true });
      writeFileSync(join(runtime, "data", "db", "codex-mem.sqlite3"), "");
      mkdirSync(join(runtime, "runtime", "mcp-server", "dist"), {
        recursive: true,
      });
      writeFileSync(
        join(runtime, "runtime", "mcp-server", "dist", "server.js"),
        "",
      );
      mkdirSync(join(runtime, "runtime", "plugin", ".codex-plugin"), {
        recursive: true,
      });
      writeFileSync(
        join(runtime, "runtime", "plugin", ".codex-plugin", "plugin.json"),
        "{}",
      );
      writeFileSync(join(runtime, "runtime", "plugin", "hooks.json"), "{}");
      writeFileSync(
        join(runtime, "worker.json"),
        JSON.stringify({
          pid: 123,
          port: 8123,
          apiUrl: "http://127.0.0.1:8123",
          logsDir: join(runtime, "logs"),
        }),
      );

      globalThis.fetch = mock(async () => new Response("ok")) as typeof fetch;
      console.log = mock((message = "") => {
        logs.push(message);
      }) as unknown as typeof console.log;

      await doctorCommand();

      expect(logs).toContain(`Runtime: ${runtime}`);
      expect(logs).toContain("API URL: http://127.0.0.1:8123");
      expect(logs).toContain("API: ok");
      expect(logs).toContain(
        `DB directory: ok (${join(runtime, "data", "db")})`,
      );
      expect(logs).toContain(
        `DB file: ok (${join(runtime, "data", "db", "codex-mem.sqlite3")})`,
      );
      expect(logs).toContain(
        `MCP server: ok (${join(runtime, "runtime", "mcp-server", "dist", "server.js")})`,
      );
      expect(logs).toContain(
        `Plugin config: ok (${join(runtime, "runtime", "plugin", ".codex-plugin", "plugin.json")})`,
      );
      expect(logs).toContain(
        `Hooks: ok (${join(runtime, "runtime", "plugin", "hooks.json")})`,
      );
      expect(logs).toContain("Port: 8123");
    } finally {
      rmSync(runtime, { recursive: true, force: true });
    }
  });
});
