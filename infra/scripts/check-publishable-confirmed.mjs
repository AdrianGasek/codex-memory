process.env.CODEX_MEMORY_NPM_AVAILABILITY_CONFIRMED = "true";

if (!process.argv[2]) {
  process.argv[2] = "apps/cli/package.json";
}

await import("./check-publishable-package.mjs");
