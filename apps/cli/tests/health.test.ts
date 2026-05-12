import { afterEach, describe, expect, mock, test } from "bun:test";
import { healthCommand } from "../src/commands/health";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
const originalApiUrl = process.env.CODEX_MEM_API_URL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  if (originalApiUrl === undefined) delete process.env.CODEX_MEM_API_URL;
  else process.env.CODEX_MEM_API_URL = originalApiUrl;
});

describe("healthCommand", () => {
  test("prints health components and cleanup recommendations", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];
    globalThis.fetch = mock(async () =>
      new Response(
        JSON.stringify({
          status: "warning",
          components: [
            { name: "db", status: "ok", detail: "sqlite" },
            { name: "schema", status: "ok", detail: "schema_version=2" },
            { name: "vector", status: "warning", detail: "local" },
            { name: "hooks", status: "ok", detail: "hooks.json" },
            { name: "mcp", status: "ok", detail: ".mcp.json" },
            { name: "plugin", status: "ok", detail: "plugin.json" },
          ],
          index_state: "indexed",
          cleanup_recommendations: ["prune --stale 90d", "compact --max-tokens 800", "dedupe"],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => logs.push(message)) as unknown as typeof console.log;

    await healthCommand();

    expect(logs).toContain("Memory health: warning");
    expect(logs).toContain("- db: ok (sqlite)");
    expect(logs).toContain("Indexing state: indexed");
    expect(logs).toContain("- prune --stale 90d");
  });

  test("prints JSON health output", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];
    globalThis.fetch = mock(async () =>
      new Response(JSON.stringify({ status: "ok", components: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => logs.push(message)) as unknown as typeof console.log;

    await healthCommand(["--json"]);

    expect(JSON.parse(logs[0]).status).toBe("ok");
  });
});
