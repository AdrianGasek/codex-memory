import { afterEach, describe, expect, mock, test } from "bun:test";
import { getCommand } from "../src/commands/get";

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

describe("getCommand", () => {
  test("fetches a memory by id and prints its fields", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          id: "mem-get",
          type: "decision",
          title: "Read by id",
          context: "Lookup should use the encoded memory id.",
          resolution: "Print the memory details.",
          confidence: 0.85,
          importance: 0.5,
          pinned: false,
          file_paths: ["apps/cli/src/commands/get.ts"],
          tags: ["cli"],
          source: "test",
          timestamp: "2026-05-06T00:00:00Z",
          project: "tests",
          status: "active",
          conflict_ids: [],
          superseded_by: null,
          retrieved_count: 0,
          injected_count: 0,
          last_used_timestamp: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message: string) => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await getCommand(["mem-get"]);

    expect(urls).toEqual(["http://memory.test/memory/mem-get"]);
    expect(logs).toEqual([
      "[decision] Read by id",
      "id=mem-get confidence=0.85 importance=0.5",
      "context: Lookup should use the encoded memory id.",
      "resolution: Print the memory details.",
      "files: apps/cli/src/commands/get.ts",
      "tags: cli",
    ]);
  });
});
