import { afterEach, describe, expect, mock, test } from "bun:test";
import { optimizeContextCommand } from "../src/commands/optimizeContext";

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

describe("optimizeContextCommand", () => {
  test("requests a balanced injection preview with budget", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return jsonResponse({
        task: "Fix auth",
        token_budget: 6000,
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

    await optimizeContextCommand([
      "Fix auth",
      "--budget",
      "6000",
      "--strategy",
      "balanced",
      "--json",
    ]);

    expect(urls).toEqual([
      "http://memory.test/memory/inject-preview?query=Fix+auth&profile=normal&token_budget=6000",
    ]);
    const payload = JSON.parse(logs[0]);
    expect(payload.strategy).toBe("balanced");
    expect(payload.tokenBudget).toBe(6000);
    expect(payload.budgetWarning).toBeNull();
    expect(payload.report.selectedTokens).toBe(42);
    expect(payload.report.skippedTokens).toBe(0);
    expect(payload.selectedContext[0].classification).toBe("must_include");
    expect(payload.selectedContext[0].filePaths).toEqual(["src/auth.ts"]);
  });

  test("classifies lower-ranked selected context as nice to include", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];

    globalThis.fetch = mock(async () =>
      jsonResponse({
        task: "Tune context",
        token_budget: 6000,
        candidate_count: 2,
        selected_context: [
          {
            id: "mem_1",
            type: "decision",
            title: "Primary decision",
            tokens: 50,
            relevance: 0.9,
            reason: "strong match",
            mode: "full",
            file_paths: [],
            tags: [],
          },
          {
            id: "mem_2",
            type: "fact",
            title: "Supporting fact",
            tokens: 25,
            relevance: 0.6,
            reason: "weak match",
            mode: "summary",
            file_paths: [],
            tags: [],
          },
        ],
        excluded_context: [],
        selected_estimated_tokens: 75,
        total_estimated_tokens: 75,
        additional_context: "",
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await optimizeContextCommand(["Tune context", "--json"]);

    const payload = JSON.parse(logs[0]);
    expect(payload.selectedContext[0].classification).toBe("must_include");
    expect(payload.selectedContext[1].classification).toBe("nice_to_include");
  });

  test("prints text optimization report", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];

    globalThis.fetch = mock(async () =>
      jsonResponse({
        task: "Refactor checkout",
        token_budget: 6000,
        candidate_count: 1,
        selected_context: [],
        excluded_context: [],
        selected_estimated_tokens: 0,
        total_estimated_tokens: 0,
        additional_context: "",
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await optimizeContextCommand(["--query", "Refactor checkout"]);

    expect(logs[0]).toBe("Task: Refactor checkout");
    expect(logs[1]).toBe("Strategy: balanced");
    expect(logs[3]).toBe(
      "Token report: selected=0; skipped=0; savedByDedupe=0; staleSkips=0; conflicts=0",
    );
    expect(logs[4]).toBe("Selected context: none");
  });

  test("reports skipped, stale, and conflict token signals", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];

    globalThis.fetch = mock(async () =>
      jsonResponse({
        task: "Tune context",
        token_budget: 6000,
        candidate_count: 3,
        selected_context: [
          {
            id: "mem_1",
            type: "decision",
            title: "Decision",
            tokens: 40,
            relevance: 0.9,
            reason: "matched",
            mode: "full",
            file_paths: [],
            tags: [],
          },
        ],
        excluded_context: [
          {
            id: "mem_2",
            type: "fact",
            title: "Stale fact",
            tokens: 20,
            relevance: 0.4,
            reason: "stale memory skipped",
          },
          {
            id: "mem_3",
            type: "decision",
            title: "Conflicting decision",
            tokens: 30,
            relevance: 0.7,
            reason: "conflict with newer decision",
          },
        ],
        selected_estimated_tokens: 40,
        total_estimated_tokens: 90,
        additional_context: "",
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await optimizeContextCommand(["Tune context", "--json"]);

    const payload = JSON.parse(logs[0]);
    expect(payload.report).toEqual({
      selectedTokens: 40,
      skippedTokens: 50,
      savedByDedupeTokens: 0,
      staleSkips: 1,
      conflicts: 1,
    });
  });

  test("warns when selected context is close to the token budget", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const logs: string[] = [];

    globalThis.fetch = mock(async () =>
      jsonResponse({
        task: "Tune context",
        token_budget: 100,
        candidate_count: 1,
        selected_context: [],
        excluded_context: [],
        selected_estimated_tokens: 95,
        total_estimated_tokens: 95,
        additional_context: "",
      }),
    ) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await optimizeContextCommand(["Tune context"]);

    expect(logs[4]).toBe(
      "Budget warning: selected context is within 10% of the 100 token budget",
    );
  });

  test.each([
    ["minimal", "short"],
    ["balanced", "normal"],
    ["deep", "deep"],
    ["safety-first", "deep"],
  ])("maps %s strategy to %s retrieval profile", async (strategy, profile) => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      urls.push(String(url));
      return jsonResponse({
        task: "Tune context",
        token_budget: 6000,
        candidate_count: 0,
        selected_context: [],
        excluded_context: [],
        selected_estimated_tokens: 0,
        total_estimated_tokens: 0,
        additional_context: "",
      });
    }) as unknown as typeof fetch;
    console.log = mock(() => {}) as unknown as typeof console.log;

    await optimizeContextCommand(["Tune context", "--strategy", strategy]);

    expect(urls[0]).toBe(
      `http://memory.test/memory/inject-preview?query=Tune+context&profile=${profile}`,
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
