import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const packagePath = resolve(process.argv[2] ?? "apps/cli/package.json");
const manifest = JSON.parse(readFileSync(packagePath, "utf8"));

if (manifest.private === true) {
  console.error(`${packagePath} has private: true and cannot be published.`);
  process.exit(1);
}

if (!manifest.name || !manifest.version) {
  console.error(`${packagePath} must include name and version before publishing.`);
  process.exit(1);
}

if (manifest.name === "codex-mem" && process.env.CODEX_MEM_NPM_OWNERSHIP_CONFIRMED !== "true") {
  console.error("Set CODEX_MEM_NPM_OWNERSHIP_CONFIRMED=true only after confirming npm ownership for codex-mem.");
  process.exit(1);
}

console.log(`${manifest.name}@${manifest.version} is publishable.`);
