import { afterEach, describe, expect, mock, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { devDoctor } from "../src/commands/dev";

const originalLog = console.log;

afterEach(() => {
  console.log = originalLog;
});

describe("devDoctor", () => {
  test("passes for a complete developer toolkit checkout", () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-dev-"));
    const logs: string[] = [];
    try {
      writeToolkit(repo, { "api:dev": "x", "mcp:dev": "x", "cli:test": "x", "api:test": "x" });
      console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

      devDoctor(repo);

      expect(logs).toEqual(["Developer Toolkit: ok"]);
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });

  test("fails clearly for an incomplete checkout", () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-dev-"));
    try {
      writeFileSync(join(repo, "package.json"), JSON.stringify({ scripts: {} }), "utf8");
      expect(() => devDoctor(repo)).toThrow("Developer Toolkit checkout is incomplete");
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });
});

function writeToolkit(repo: string, scripts: Record<string, string>): void {
  writeFileSync(join(repo, "package.json"), JSON.stringify({ scripts }), "utf8");
  for (const path of [
    "apps/api/pyproject.toml",
    "apps/cli/package.json",
    "apps/mcp-server/package.json",
    "plugins/codex-mem/.codex-plugin/plugin.json",
  ]) {
    mkdirSync(join(repo, path, ".."), { recursive: true });
    writeFileSync(join(repo, path), "{}", "utf8");
  }
}
