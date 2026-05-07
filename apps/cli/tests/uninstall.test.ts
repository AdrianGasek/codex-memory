import { afterEach, describe, expect, mock, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { uninstallCommand } from "../src/commands/uninstall";

const originalLog = console.log;

afterEach(() => {
  console.log = originalLog;
});

describe("uninstallCommand", () => {
  test("removes codex-mem from marketplace and writes a backup", () => {
    const repo = mkdtempSync(join(tmpdir(), "codex-mem-uninstall-"));
    const logs: string[] = [];
    try {
      writeFileSync(join(repo, "package.json"), "{\"name\":\"demo\"}\n", "utf8");
      mkdirSync(join(repo, ".agents", "plugins"), { recursive: true });
      const marketplacePath = join(repo, ".agents", "plugins", "marketplace.json");
      writeFileSync(
        marketplacePath,
        JSON.stringify({ plugins: [{ name: "codex-mem" }, { name: "other" }] }, null, 2),
        "utf8",
      );
      console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

      uninstallCommand(["--cwd", repo]);

      const updated = JSON.parse(readFileSync(marketplacePath, "utf8"));
      expect(updated.plugins).toEqual([{ name: "other" }]);
      expect(existsSync(`${marketplacePath}.bak`)).toBe(true);
      expect(logs[0]).toContain("Backup:");
    } finally {
      rmSync(repo, { recursive: true, force: true });
    }
  });
});
