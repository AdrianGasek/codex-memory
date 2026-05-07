import { afterEach, describe, expect, mock, test } from "bun:test";
import { runCommand } from "../src/index";

const originalLog = console.log;

afterEach(() => {
  console.log = originalLog;
});

describe("version command", () => {
  test("prints package version for npx smoke checks", async () => {
    const logs: string[] = [];
    console.log = mock((message: string) => {
      logs.push(message);
    }) as unknown as typeof console.log;

    await runCommand("--version", []);

    expect(logs).toEqual(["0.1.0"]);
  });
});
