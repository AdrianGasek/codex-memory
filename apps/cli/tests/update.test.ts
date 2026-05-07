import { afterEach, describe, expect, mock, test } from "bun:test";
import { updateCommand } from "../src/commands/update";

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

describe("updateCommand", () => {
  test("patches only provided memory fields", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request, init?: RequestInit) => {
      requests.push({ url: String(url), init });
      return new Response(
        JSON.stringify({
          id: "mem-update",
          type: "pattern",
          title: "Updated pattern",
          context: "Updated context.",
          resolution: "Updated resolution.",
          confidence: 0.95,
          importance: 0.7,
          pinned: true,
          file_paths: ["apps/cli/src/commands/update.ts"],
          tags: ["cli", "update"],
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
    }) as unknown as typeof fetch;
    console.log = mock((message: string) => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await updateCommand([
      "mem-update",
      "--type",
      "pattern",
      "--title",
      "Updated pattern",
      "--context",
      "Updated context.",
      "--resolution",
      "Updated resolution.",
      "--confidence",
      "0.95",
      "--importance",
      "0.7",
      "--pinned",
      "true",
      "--path",
      "apps/cli/src/commands/update.ts",
      "--tag",
      "cli,update",
      "--source",
      "cli-test",
      "--project",
      "tests",
    ]);

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe("http://memory.test/memory/mem-update");
    expect(requests[0]?.init?.method).toBe("PATCH");
    expect(JSON.parse(String(requests[0]?.init?.body))).toEqual({
      type: "pattern",
      title: "Updated pattern",
      context: "Updated context.",
      resolution: "Updated resolution.",
      confidence: 0.95,
      importance: 0.7,
      pinned: true,
      file_paths: ["apps/cli/src/commands/update.ts"],
      tags: ["cli", "update"],
      source: "cli-test",
      project: "tests",
    });
    expect(logs).toEqual(["Updated mem-update: Updated pattern"]);
  });
});
