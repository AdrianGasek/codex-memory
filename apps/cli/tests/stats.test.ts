import { afterEach, describe, expect, mock, test } from "bun:test";
import { statsCommand } from "../src/commands/stats";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
const originalApiUrl = process.env.CODEX_MEM_API_URL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  if (originalApiUrl === undefined) {
    delete process.env.CODEX_MEM_API_URL;
  } else {
    process.env.CODEX_MEM_API_URL = originalApiUrl;
  }
});

describe("statsCommand", () => {
  test("prints basic memory stats", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          calls_by_command: { inject: 2, search: 4 },
          total_injected_memories: 3,
          average_injected_tokens: 24,
          max_injected_tokens: 50,
          skipped_due_to_budget: 1,
          most_recalled_files: [{ file_path: "src/auth.ts", count: 3 }],
          most_used_memory_types: [{ type: "decision", count: 5 }],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await statsCommand();

    expect(urls).toEqual(["http://memory.test/memory/stats"]);
    expect(logs).toContain("Memory stats");
    expect(logs).toContain("Total injected memories: 3");
    expect(logs).toContain("Skipped due to budget: 1");
    expect(logs).toContain("Memory calls by command:");
    expect(logs).toContain("- inject: 2");
    expect(logs).toContain("- search: 4");
    expect(logs).toContain("Most recalled files:");
    expect(logs).toContain("- src/auth.ts: 3");
    expect(logs).toContain("Most used memory types:");
    expect(logs).toContain("- decision: 5");
  });

  test("passes project and since filters and prints JSON", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          calls_by_command: {},
          total_injected_memories: 0,
          average_injected_tokens: 0,
          max_injected_tokens: 0,
          skipped_due_to_budget: 0,
          most_recalled_files: [],
          most_used_memory_types: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await statsCommand(["--project", "demo", "--since", "7d", "--json"]);

    expect(urls).toEqual([
      "http://memory.test/memory/stats?project=demo&since=7d",
    ]);
    expect(JSON.parse(logs[0]).total_injected_memories).toBe(0);
  });

  test("requests and prints impact stats", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          calls_by_command: {},
          total_injected_memories: 0,
          average_injected_tokens: 0,
          max_injected_tokens: 0,
          skipped_due_to_budget: 0,
          most_recalled_files: [],
          most_used_memory_types: [],
          impact: {
            memory_assisted_sessions: 2,
            boundary_warnings: 1,
            repeated_bug_reuse: 3,
            average_context_size: 42,
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await statsCommand(["--impact"]);

    expect(urls).toEqual(["http://memory.test/memory/stats?impact=true"]);
    expect(logs).toContain("Impact:");
    expect(logs).toContain("- memory-assisted sessions: 2");
    expect(logs).toContain("- boundary warnings: 1");
    expect(logs).toContain("- repeated bug reuse: 3");
    expect(logs).toContain("- average context size: 42");
  });
});
