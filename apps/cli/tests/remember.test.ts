import { afterEach, describe, expect, mock, test } from "bun:test";
import { rememberCommand } from "../src/commands/remember";

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

describe("rememberCommand", () => {
  test("posts a memory payload and prints the stored entry", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test/";
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const logs: string[] = [];

    globalThis.fetch = mock(
      async (url: string | URL | Request, init?: RequestInit) => {
        requests.push({ url: String(url), init });
        return new Response(
          JSON.stringify({
            id: "mem-1",
            type: "decision",
            title: "Use CLI tests",
            context: "Cover remember command.",
            resolution: "Mock the memory API.",
            confidence: 0.8,
            importance: 0,
            pinned: false,
            file_paths: ["apps/cli/src/index.ts"],
            tags: ["cli", "test"],
            source: "cli-test",
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

    await rememberCommand([
      "--type",
      "decision",
      "--title",
      "Use CLI tests",
      "--context",
      "Cover remember command.",
      "--resolution",
      "Mock the memory API.",
      "--confidence",
      "0.8",
      "--path",
      "apps/cli/src/index.ts",
      "--tag",
      "cli,test",
      "--source",
      "cli-test",
      "--project",
      "tests",
    ]);

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe("http://memory.test/memory");
    expect(requests[0]?.init?.method).toBe("POST");
    expect(JSON.parse(String(requests[0]?.init?.body))).toEqual({
      type: "decision",
      title: "Use CLI tests",
      context: "Cover remember command.",
      resolution: "Mock the memory API.",
      confidence: 0.8,
      file_paths: ["apps/cli/src/index.ts"],
      tags: ["cli", "test"],
      source: "cli-test",
      project: "tests",
    });
    expect(logs).toEqual(["Stored mem-1: Use CLI tests"]);
  });
});
