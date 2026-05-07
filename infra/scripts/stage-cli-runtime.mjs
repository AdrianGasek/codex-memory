import { cpSync, mkdirSync, rmSync } from "node:fs";
import { basename, resolve } from "node:path";

const repoRoot = resolve(import.meta.dirname, "../..");
const runtimeDir = resolve(repoRoot, "apps/cli/runtime");

function shouldCopy(source) {
  const name = basename(source);
  return name !== "__pycache__" && !name.endsWith(".pyc");
}

function copy(source, destination) {
  cpSync(resolve(repoRoot, source), resolve(runtimeDir, destination), {
    recursive: true,
    filter: shouldCopy,
  });
}

rmSync(runtimeDir, { recursive: true, force: true });
mkdirSync(runtimeDir, { recursive: true });

copy("apps/mcp-server/dist", "mcp-server/dist");
copy("plugins/codex-mem", "plugin");
copy("apps/api/app", "api/app");
copy("apps/api/pyproject.toml", "api/pyproject.toml");
copy("apps/api/uv.lock", "api/uv.lock");
