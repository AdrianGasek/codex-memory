import { describe, expect, test } from "bun:test";
import { createServer } from "node:net";
import { resolveApiEndpoint, waitForHealth } from "../src/commands/worker";

describe("worker health checks", () => {
  test("checks API health and memory diagnostics", async () => {
    const urls: string[] = [];
    const fetcher = (async (url: string | URL | Request) => {
      urls.push(String(url));
      return new Response("{}", { status: 200 });
    }) as typeof fetch;

    await waitForHealth("http://127.0.0.1:8000", fetcher, 1);

    expect(urls).toEqual([
      "http://127.0.0.1:8000/health",
      "http://127.0.0.1:8000/memory/health/diagnostics",
    ]);
  });

  test("fails clearly when health checks never pass", async () => {
    const fetcher = (async () => new Response("{}", { status: 503 })) as typeof fetch;
    await expect(waitForHealth("http://127.0.0.1:8000", fetcher, 1)).rejects.toThrow("did not pass health checks");
  });

  test("reuses a healthy Codex-Mem API on the preferred port", async () => {
    const fetcher = (async () => new Response("{}", { status: 200 })) as typeof fetch;
    await expect(resolveApiEndpoint(8000, fetcher)).resolves.toEqual({
      port: 8000,
      apiUrl: "http://127.0.0.1:8000",
      reuseExisting: true,
    });
  });

  test("chooses the next free port when preferred port is occupied by another process", async () => {
    const server = createServer();
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    const occupiedPort = typeof address === "object" && address ? address.port : 0;
    const fetcher = (async () => {
      throw new Error("not Codex-Mem");
    }) as typeof fetch;

    try {
      const endpoint = await resolveApiEndpoint(occupiedPort, fetcher);
      expect(endpoint.port).toBeGreaterThan(occupiedPort);
      expect(endpoint.reuseExisting).toBe(false);
    } finally {
      server.close();
    }
  });
});
