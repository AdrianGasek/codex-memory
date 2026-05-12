import { afterEach, describe, expect, mock, test } from "bun:test";
import { runCommand } from "../src/index";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
const originalApiUrl = process.env.CODEX_MEM_API_URL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  if (originalApiUrl === undefined) delete process.env.CODEX_MEM_API_URL;
  else process.env.CODEX_MEM_API_URL = originalApiUrl;
});

describe("extra observability commands", () => {
  test("prints reports for diff dashboard risk map audit and cleanup", async () => {
    const logs: string[] = [];
    console.log = mock((message = "") => logs.push(message)) as unknown as typeof console.log;

    await runCommand("diff", ["HEAD~1"]);
    await runCommand("dashboard", ["--summary"]);
    await runCommand("risk-map", []);
    await runCommand("audit-session", ["session_1"]);
    await runCommand("prune", ["--stale", "90d"]);
    await runCommand("compact", ["--max-tokens", "800"]);
    await runCommand("dedupe", []);
    await runCommand("promote", ["mem_1", "--to", "AGENTS.md"]);

    expect(logs).toContain("Memory diff against HEAD~1");
    expect(logs).toContain("Dashboard summary: current project brain, recent recalls, token usage, risk map, stale memories, top recalled files, current task scope");
    expect(logs).toContain("Risk map");
    expect(logs).toContain("Session audit: session_1");
    expect(logs).toContain("prune dry-run");
    expect(logs).toContain("compact dry-run");
    expect(logs).toContain("dedupe dry-run");
    expect(logs).toContain("Promotion suggested for mem_1: AGENTS.md");
  });

  test("updates pin block and stale markers", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(JSON.stringify({ id: "mem_1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;
    console.log = mock(() => {}) as unknown as typeof console.log;

    await runCommand("pin", ["mem_1"]);
    await runCommand("never-inject", ["mem_1"]);
    await runCommand("mark-stale", ["mem_1"]);

    expect(urls).toEqual([
      "http://memory.test/memory/mem_1",
      "http://memory.test/memory/mem_1",
      "http://memory.test/memory/mem_1",
    ]);
  });

  test("reports memory mode status", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];
    globalThis.fetch = mock(async () =>
      new Response(
        JSON.stringify({
          status: "ok",
          index_state: "indexed",
          components: [{ name: "db", status: "ok", detail: "sqlite" }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => logs.push(message)) as unknown as typeof console.log;

    await runCommand("status", ["--memory-mode"]);

    expect(logs).toContain("Memory mode: writable");
    expect(logs).toContain("- indexed: true");
    expect(logs).toContain("- preview-enabled: true");
    expect(logs).toContain("- budget-limited: true");
  });
});
