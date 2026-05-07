import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const packages = process.argv.slice(2);
const packagePaths = packages.length > 0 ? packages : ["apps/cli", "apps/mcp-server"];
const releaseDir = resolve("dist/release");
mkdirSync(releaseDir, { recursive: true });

for (const packagePath of packagePaths) {
  const result = spawnSync(
    "bun",
    ["pm", "pack", "--destination", releaseDir, "--ignore-scripts"],
    { cwd: resolve(packagePath), stdio: "inherit" }
  );

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}
