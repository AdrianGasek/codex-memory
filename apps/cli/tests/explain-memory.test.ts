import { afterEach, describe, expect, mock, test } from "bun:test";
import { explainMemoryCommand } from "../src/commands/explainMemory";

const originalFetch = globalThis.fetch;
const originalLog = console.log;
const originalApiUrl = process.env.CODEX_MEM_API_URL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  console.log = originalLog;
  if (originalApiUrl === undefined) delete process.env.CODEX_MEM_API_URL;
  else process.env.CODEX_MEM_API_URL = originalApiUrl;
});

describe("explainMemoryCommand", () => {
  test("prints deterministic explanation fields", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];
    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          id: "mem_1",
          ranking_reason: "matched stable rule",
          matching_query_terms: ["auth"],
          file_path_evidence: ["src/auth.ts"],
          usage_evidence: ["retrieved_count=1"],
          conflict_staleness_signals: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => logs.push(message)) as unknown as typeof console.log;

    await explainMemoryCommand(["mem_1"]);

    expect(urls).toEqual(["http://memory.test/memory/explain/mem_1"]);
    expect(logs).toContain("Memory: mem_1");
    expect(logs).toContain("File/path evidence: src/auth.ts");
  });
});
