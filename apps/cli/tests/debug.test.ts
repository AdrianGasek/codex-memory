import { afterEach, describe, expect, mock, test } from "bun:test";
import { debugCommand } from "../src/commands/debug";

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

describe("debugCommand", () => {
  test("prints health, config diagnostics, and injection context", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    const urls: string[] = [];
    const logs: string[] = [];

    globalThis.fetch = mock(async (url: string | URL | Request) => {
      const href = String(url);
      urls.push(href);
      if (href.endsWith("/health")) {
        return jsonResponse({ status: "ok" });
      }
      if (href.endsWith("/memory/config/diagnostics")) {
        return jsonResponse({
          config_path: ".codex/mem.config.json",
          diagnostics: ["Vector backend is local."],
          debug_verbose: false,
          inject_limit: 5,
          token_budget: 1200,
          vector_backend: "local",
        });
      }
      return jsonResponse({ additional_context: "Relevant Codex-Mem Context" });
    }) as unknown as typeof fetch;
    console.log = mock((message = "") => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await debugCommand(["--query", "project memory", "--limit", "2", "--profile", "deep"]);

    expect(urls).toEqual([
      "http://memory.test/health",
      "http://memory.test/memory/config/diagnostics",
      "http://memory.test/memory/inject?query=project+memory&limit=2&profile=deep",
    ]);
    expect(logs).toEqual([
      "API: ok",
      "Config: .codex/mem.config.json",
      "Config diagnostics:",
      "- Vector backend is local.",
      "",
      "Relevant Codex-Mem Context",
    ]);
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
