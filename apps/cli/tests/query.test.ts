import { afterEach, describe, expect, mock, test } from "bun:test";
import { queryCommand } from "../src/commands/query";

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

describe("queryCommand", () => {
  test("requests search results and prints ranked memory details", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response(
        JSON.stringify({
          results: [
            {
              score: 1.25,
              reason: "matched query terms",
              entry: {
                id: "mem-query",
                type: "solution",
                title: "Use hybrid ranking",
                context: "Combine keyword and recency signals.",
                resolution: "Use the ranking module.",
                confidence: 0.9,
                importance: 0.4,
                pinned: false,
                file_paths: ["apps/api/app/core/ranking.py"],
                tags: ["ranking"],
                source: "test",
                timestamp: "2026-05-06T00:00:00Z",
                project: "tests",
                status: "active",
                conflict_ids: [],
                superseded_by: null,
                retrieved_count: 0,
                injected_count: 0,
                last_used_timestamp: null,
              },
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await queryCommand([
      "hybrid",
      "ranking",
      "--limit",
      "1",
      "--profile",
      "short",
      "--path",
      "apps/api/app/core/ranking.py",
      "--after",
      "2026-01-01",
      "--before",
      "2026-12-31",
    ]);

    expect(urls).toEqual([
      "http://memory.test/memory/search?query=hybrid+ranking&limit=1&path=apps%2Fapi%2Fapp%2Fcore%2Franking.py&after=2026-01-01&before=2026-12-31&profile=short",
    ]);
    expect(logs).toContain("[solution] Use hybrid ranking");
    expect(logs).toContain("id=mem-query score=1.25 confidence=0.9");
    expect(logs).toContain("files: apps/api/app/core/ranking.py");
    expect(logs).toContain("tags: ranking");
  });
});
