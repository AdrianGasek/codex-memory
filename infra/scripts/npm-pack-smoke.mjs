import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const repoRoot = resolve(import.meta.dirname, "../..");
const packageJson = JSON.parse(readFileSync(resolve(repoRoot, "apps/cli/package.json"), "utf8"));
const tarball = resolve(repoRoot, process.argv[2] ?? `dist/release/codex-memory-${packageJson.version}.tgz`);
const tempDir = mkdtempSync(join(tmpdir(), "codex-mem-pack-smoke-"));

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: tempDir,
    shell: process.platform === "win32",
    stdio: "inherit",
    ...options,
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

try {
  run("npm", ["init", "-y"], { stdio: "ignore" });
  run("npm", ["install", tarball, "--ignore-scripts"]);
  run("npx", ["codex-memory", "--version"]);
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
