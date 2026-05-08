import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const packagePath = resolve(process.argv[2] ?? "apps/cli/package.json");
const manifest = JSON.parse(readFileSync(packagePath, "utf8"));

if (manifest.private === true) {
  console.error(`${packagePath} has private: true and cannot be published.`);
  process.exit(1);
}

if (!manifest.name || !manifest.version) {
  console.error(
    `${packagePath} must include name and version before publishing.`,
  );
  process.exit(1);
}

if (manifest.name === "codex-mem") {
  console.error(
    "The npm package name codex-mem is already taken. Use codex-memory for the public CLI package.",
  );
  process.exit(1);
}

if (
  manifest.name === "codex-memory" &&
  process.env.CODEX_MEMORY_NPM_AVAILABILITY_CONFIRMED !== "true"
) {
  console.error(
    "Set CODEX_MEMORY_NPM_AVAILABILITY_CONFIRMED=true only after confirming npm availability for codex-memory.",
  );
  process.exit(1);
}

const dependencySections = [
  "dependencies",
  "devDependencies",
  "peerDependencies",
  "optionalDependencies",
];
for (const section of dependencySections) {
  if (manifest[section]?.[manifest.name]) {
    console.error(
      `${manifest.name} must not list itself in ${section}. Run install tests from a temporary consumer project instead.`,
    );
    process.exit(1);
  }
}

console.log(`${manifest.name}@${manifest.version} is publishable.`);
