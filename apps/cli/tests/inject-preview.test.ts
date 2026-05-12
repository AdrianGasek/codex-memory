import { afterEach, describe, expect, mock, test } from "bun:test";
import { injectPreviewCommand } from "../src/commands/injectPreview";

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

describe("injectPreviewCommand", () => {
  test("prints JSON preview with camelCase agent fields", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return jsonResponse({
        task: "Fix auth",
        token_budget: 4000,
        candidate_count: 1,
        selected_context: [
          {
            id: "mem_1",
            type: "decision",
            title: "Auth decision",
            tokens: 42,
            relevance: 0.91,
            reason: "matched auth",
            mode: "full",
            file_paths: ["src/auth.ts"],
            tags: ["auth"],
          },
        ],
        excluded_context: [],
        selected_estimated_tokens: 42,
        total_estimated_tokens: 42,
        additional_context: "# Relevant Codex-Mem Context",
      });
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await injectPreviewCommand(["Fix auth", "--budget", "4000", "--json"]);

    expect(urls).toEqual([
      "http://memory.test/memory/inject-preview?query=Fix+auth&token_budget=4000",
    ]);
    const payload = JSON.parse(logs[0]);
    expect(payload.tokenBudget).toBe(4000);
    expect(payload.selectedContext[0].filePaths).toEqual(["src/auth.ts"]);
  });

  test("prints a concise text report", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];

    globalThis.fetch = mock(async () =>
      jsonResponse({
        task: "Refactor checkout",
        token_budget: 1200,
        candidate_count: 1,
        selected_context: [
          {
            id: "mem_1",
            type: "pattern",
            title: "Checkout pattern",
            tokens: 30,
            relevance: 0.8,
            reason: "matched checkout",
            mode: "summary",
            file_paths: [],
            tags: [],
          },
        ],
        excluded_context: [],
        selected_estimated_tokens: 30,
        total_estimated_tokens: 30,
        additional_context: "",
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await injectPreviewCommand(["--query", "Refactor checkout"]);

    expect(logs[0]).toBe("Task: Refactor checkout");
    expect(logs[2]).toBe("Selected context:");
    expect(logs[3]).toContain("[pattern] Checkout pattern");
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
