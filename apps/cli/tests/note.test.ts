import { afterEach, describe, expect, mock, test } from "bun:test";
import { runCommand } from "../src/index";

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

describe("note alias", () => {
  test("dispatches to remember and stores a fact by default", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const logs: string[] = [];

    globalThis.fetch = mock(
      async (url: string | URL | Request, init?: RequestInit) => {
        requests.push({ url: String(url), init });
        return new Response(
          JSON.stringify({
            id: "mem-note",
            type: "fact",
            title: "Alias works",
            context: "The note alias should use remember.",
            resolution: "",
            confidence: 0.75,
            importance: 0,
            pinned: false,
            file_paths: [],
            tags: [],
            source: "cli",
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
      },
    ) as unknown as typeof fetch;
    console.log = mock((message: string) => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await runCommand("note", [
      "--title",
      "Alias works",
      "--context",
      "The note alias should use remember.",
    ]);

    expect(requests).toHaveLength(1);
    expect(JSON.parse(String(requests[0]?.init?.body))).toMatchObject({
      type: "fact",
      title: "Alias works",
      context: "The note alias should use remember.",
      source: "cli",
    });
    expect(logs).toEqual(["Stored mem-note: Alias works"]);
  });
});
