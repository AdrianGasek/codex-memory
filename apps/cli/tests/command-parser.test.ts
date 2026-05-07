import { afterEach, describe, expect, mock, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseOptions } from "../src/commands/args";
import { runCommand } from "../src/index";

const originalLog = console.log;
const originalHome = process.env.CODEX_MEM_HOME;

afterEach(() => {
  console.log = originalLog;
  if (originalHome === undefined) {
    delete process.env.CODEX_MEM_HOME;
  } else {
    process.env.CODEX_MEM_HOME = originalHome;
  }
});

describe("command parser", () => {
  test("parses install/start/doctor/uninstall style options", () => {
    expect(parseOptions(["--yes", "--port", "8123", "--cwd", "repo"]).get("port")).toEqual(["8123"]);
    expect(parseOptions(["doctor"]).get("_")).toEqual(["doctor"]);
  });

  test("help lists product lifecycle commands", async () => {
    const logs: string[] = [];
    console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

    await runCommand("help", []);

    const help = logs.join("\n");
    expect(help).toContain("install --yes");
    expect(help).toContain("dev doctor");
    expect(help).toContain("doctor");
    expect(help).toContain("status | start | stop | restart");
    expect(help).toContain("uninstall");
    expect(help).toContain("upgrade");
  });

  test("dispatches status and stop without a running worker", async () => {
    const runtimeHome = mkdtempSync(join(tmpdir(), "codex-mem-parser-"));
    const logs: string[] = [];
    try {
      process.env.CODEX_MEM_HOME = runtimeHome;
      console.log = mock((message: string) => logs.push(message)) as unknown as typeof console.log;

      await runCommand("status", []);
      await runCommand("stop", []);

      expect(logs[0]).toContain("stopped");
      expect(logs[1]).toContain("not running");
    } finally {
      rmSync(runtimeHome, { recursive: true, force: true });
    }
  });
});
