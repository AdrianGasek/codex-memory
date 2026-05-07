import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readWorkerState, stopWorker } from "../src/commands/worker";

describe("worker state", () => {
  test("reads worker config from user runtime directory", () => {
    const runtimeDir = mkdtempSync(join(tmpdir(), "codex-mem-worker-"));
    try {
      writeFileSync(
        join(runtimeDir, "worker.json"),
        JSON.stringify({ pid: 123, port: 8123, apiUrl: "http://127.0.0.1:8123", logsDir: join(runtimeDir, "logs") }),
        "utf8",
      );

      expect(readWorkerState(runtimeDir)).toMatchObject({
        pid: 123,
        port: 8123,
        apiUrl: "http://127.0.0.1:8123",
      });
    } finally {
      rmSync(runtimeDir, { recursive: true, force: true });
    }
  });

  test("cleans stale pid files when stopping a missing worker", () => {
    const runtimeDir = mkdtempSync(join(tmpdir(), "codex-mem-worker-"));
    try {
      writeFileSync(join(runtimeDir, "worker.pid"), "99999999\n", "utf8");
      expect(stopWorker(runtimeDir)).toBe(false);
      expect(readWorkerState(runtimeDir)).toBeNull();
    } finally {
      rmSync(runtimeDir, { recursive: true, force: true });
    }
  });
});
