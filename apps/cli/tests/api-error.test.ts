import { afterEach, describe, expect, mock, test } from "bun:test";
import { rememberCommand } from "../src/commands/remember";

const originalFetch = globalThis.fetch;
const originalApiUrl = process.env.CODEX_MEM_API_URL;

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalApiUrl === undefined) {
    delete process.env.CODEX_MEM_API_URL;
  } else {
    process.env.CODEX_MEM_API_URL = originalApiUrl;
  }
});

describe("API error handling", () => {
  test("surfaces non-2xx API responses with status and body", async () => {
    process.env.CODEX_MEM_API_URL = "http://memory.test";
    globalThis.fetch = mock(async () => {
      return new Response('{"detail":"database unavailable"}', {
        status: 500,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;

    await expect(rememberCommand(["--title", "Store failure"])).rejects.toThrow(
      'Codex-Mem API 500: {"detail":"database unavailable"}',
    );
  });
});
