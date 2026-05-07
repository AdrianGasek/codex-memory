import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("plugin hook manifest", () => {
  test("uses stable codex-mem hook entrypoints", () => {
    const manifest = JSON.parse(readFileSync(join(import.meta.dir, "../../../plugins/codex-mem/hooks.json"), "utf8"));
    const commands = JSON.stringify(manifest);

    expect(commands).toContain("codex-mem hook session-start");
    expect(commands).toContain("codex-mem hook user-prompt");
    expect(commands).toContain("codex-mem hook stop");
    expect(commands).toContain("codex-mem hook post-tool-use");
    expect(commands).not.toContain("plugins/codex-mem/scripts/hook_memory.py");
  });
});
