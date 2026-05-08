import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { findRepoRoot } from "./install.js";

const requiredScripts = ["api:dev", "mcp:dev", "cli:test", "api:test"];
const requiredPaths = [
  "apps/api/pyproject.toml",
  "apps/cli/package.json",
  "apps/mcp-server/package.json",
  "plugins/codex-mem/.codex-plugin/plugin.json",
];

export function devCommand(args: string[]): void {
  const [subcommand] = args;
  if (subcommand !== "doctor") {
    throw new Error("Unknown dev command. Use codex-memory dev doctor.");
  }
  devDoctor(process.cwd());
}

export function devDoctor(cwd: string): void {
  const repoRoot = findRepoRoot(cwd);
  const manifest = JSON.parse(
    readFileSync(join(repoRoot, "package.json"), "utf8"),
  ) as { scripts?: Record<string, string> };
  const missingScripts = requiredScripts.filter(
    (script) => !manifest.scripts?.[script],
  );
  const missingPaths = requiredPaths.filter(
    (path) => !existsSync(join(repoRoot, path)),
  );

  if (missingScripts.length || missingPaths.length) {
    for (const script of missingScripts) {
      console.log(`missing script: ${script}`);
    }
    for (const path of missingPaths) {
      console.log(`missing path: ${path}`);
    }
    throw new Error("Developer Toolkit checkout is incomplete.");
  }

  console.log("Developer Toolkit: ok");
}
