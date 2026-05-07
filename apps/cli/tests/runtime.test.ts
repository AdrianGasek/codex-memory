import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ensureToolchain, userRuntimeDir } from "../src/commands/runtime";

describe("runtime bootstrap", () => {
  test("uses existing Bun and uv commands when present", () => {
    const calls: Array<{ command: string; args: string[] }> = [];
    const runner = ((command: string, args: string[]) => {
      calls.push({ command, args });
      return {
        status: 0,
        stdout: command === "where.exe" && args[0] === "bun" ? "C:\\bin\\bun.exe\n" : "C:\\bin\\uv.exe\n",
      };
    }) as never;

    expect(ensureToolchain({ runner })).toEqual({
      bun: "C:\\bin\\bun.exe",
      uv: "C:\\bin\\uv.exe",
    });
    expect(calls).toHaveLength(2);
  });

  test("reports a clear error when Bun is missing and npm cannot be found", () => {
    const runtimeDir = mkdtempSync(join(tmpdir(), "codex-mem-runtime-"));
    try {
      const runner = (() => ({ status: 1, stdout: "" })) as never;
      expect(() => ensureToolchain({ runtimeDir, runner })).toThrow("npm was not found");
    } finally {
      rmSync(runtimeDir, { recursive: true, force: true });
    }
  });

  test("uses CODEX_MEM_HOME as the runtime directory override", () => {
    expect(userRuntimeDir({ CODEX_MEM_HOME: "C:\\codex-mem-test" })).toBe("C:\\codex-mem-test");
  });
});
