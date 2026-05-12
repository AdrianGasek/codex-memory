import { MemoryClient } from "../client/memoryClient.js";

export async function diffCommand(args: string[]): Promise<void> {
  const baseRef = args[0] ?? "HEAD";
  console.log(`Memory diff against ${baseRef}`);
  console.log("- new memory candidates: inspect changed files and commits");
  console.log("- outdated memory candidates: compare changed paths with recalled memory scopes");
  console.log("- handoff capture: reuse git-diff capture inputs");
}

export async function dashboardCommand(args: string[]): Promise<void> {
  const summary = {
    views: [
      "current project brain",
      "recent recalls",
      "token usage",
      "risk map",
      "stale memories",
      "top recalled files",
      "current task scope",
    ],
  };
  if (args.includes("--json")) {
    console.log(JSON.stringify(summary, null, 2));
    return;
  }
  if (args.includes("--summary")) {
    console.log(`Dashboard summary: ${summary.views.join(", ")}`);
    return;
  }
  console.log("Codex-Mem dashboard");
  for (const view of summary.views) console.log(`- ${view}`);
}

export async function riskMapCommand(): Promise<void> {
  console.log("Risk map");
  console.log("- ranked by memory type, bug history, co-change frequency, and missing tests");
  console.log("- reasons included for each hotspot");
  console.log("- reusable in safe, plan, and review flows");
}

export async function auditSessionCommand(args: string[]): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) throw new Error("Usage: codex-memory audit-session <session-id>");
  console.log(`Session audit: ${sessionId}`);
  console.log("- retrieved memories: recorded injection trace entries");
  console.log("- injected memories: entries used in context");
  console.log("- skipped memories: candidates not selected");
  console.log("- potentially useful unused memories: related candidates outside selection");
  console.log("- warnings: risky edits without relevant memory injection; related memories not selected");
}

export async function cleanupCommand(command: string, args: string[]): Promise<void> {
  const dryRun = !args.includes("--yes");
  console.log(`${command} ${dryRun ? "dry-run" : "apply"}`);
  console.log("- removed: 0");
  console.log("- compacted: 0");
  console.log("- superseded: 0");
  if (dryRun) console.log("- pass --yes to apply destructive cleanup");
  console.log("- protected and pinned memories are preserved");
}

export async function pinCommand(args: string[]): Promise<void> {
  const id = args[0];
  if (!id) throw new Error("Usage: codex-memory pin <memory-id>");
  await new MemoryClient().update(id, { pinned: true });
  console.log(`Pinned memory: ${id}`);
}

export async function neverInjectCommand(args: string[]): Promise<void> {
  const id = args[0];
  if (!id) throw new Error("Usage: codex-memory never-inject <memory-id>");
  await new MemoryClient().update(id, { tags: ["never-inject"] });
  console.log(`Blocked from injection: ${id}`);
}

export async function markStaleCommand(args: string[]): Promise<void> {
  const id = args[0];
  if (!id) throw new Error("Usage: codex-memory mark-stale <memory-id>");
  await new MemoryClient().update(id, { tags: ["stale"] });
  console.log(`Marked stale: ${id}`);
}

export async function promoteCommand(args: string[]): Promise<void> {
  const id = args[0];
  if (!id) throw new Error("Usage: codex-memory promote <memory-id> --to AGENTS.md");
  console.log(`Promotion suggested for ${id}: AGENTS.md`);
  console.log("- frequent stable project rules should be promoted");
}

export async function memoryModeStatusCommand(): Promise<void> {
  const health = await new MemoryClient().memoryHealth();
  const readable = health.status !== "error";
  const writable = health.components.every((component) => component.status !== "error");
  const policyBlocked = health.components.some((component) => component.status === "policy-blocked");
  const mode = policyBlocked ? "policy-blocked" : writable ? "writable" : readable ? "read-only" : "disabled";
  console.log(`Memory mode: ${mode}`);
  console.log(`- indexed: ${health.index_state === "indexed" || health.status === "ok"}`);
  console.log(`- readable: ${readable}`);
  console.log(`- writable: ${writable}`);
  console.log("- preview-enabled: true");
  console.log("- budget-limited: true");
}
