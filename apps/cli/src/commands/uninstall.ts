import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { findRepoRoot } from "./install.js";
import { userRuntimeDir } from "./runtime.js";

export function uninstallCommand(args: string[]): void {
  const cwdIndex = args.indexOf("--cwd");
  const cwd = cwdIndex >= 0 ? args[cwdIndex + 1] : process.cwd();
  const repoRoot = findRepoRoot(cwd);
  const marketplacePath = join(repoRoot, ".agents", "plugins", "marketplace.json");
  if (!existsSync(marketplacePath)) {
    console.log("Codex-Mem plugin is not installed.");
    return;
  }

  const backupPath = `${marketplacePath}.bak`;
  const original = readFileSync(marketplacePath, "utf8");
  writeFileSync(backupPath, original, "utf8");

  const marketplace = JSON.parse(original) as { plugins?: Array<{ name?: string }> };
  marketplace.plugins = (marketplace.plugins ?? []).filter((plugin) => !["codex-memory", "codex-mem"].includes(String(plugin.name)));
  mkdirSync(dirname(marketplacePath), { recursive: true });
  writeFileSync(marketplacePath, `${JSON.stringify(marketplace, null, 2)}\n`, "utf8");
  if (args.includes("--delete-data")) {
    rmSync(join(userRuntimeDir(), "data"), { recursive: true, force: true });
  }
  console.log(`Codex-Mem plugin removed. Backup: ${relative(process.cwd(), backupPath) || backupPath}`);
}
