import { MemoryClient, type MemoryHealth } from "../client/memoryClient.js";

export async function healthCommand(args: string[] = []): Promise<void> {
  const health = await new MemoryClient().memoryHealth();
  if (args.includes("--json")) {
    console.log(JSON.stringify(health, null, 2));
    return;
  }
  printHealth(health);
}

function printHealth(health: MemoryHealth): void {
  console.log(`Memory health: ${health.status}`);
  for (const component of health.components) {
    console.log(`- ${component.name}: ${component.status} (${component.detail})`);
  }
  console.log(`Indexing state: ${health.index_state ?? "unknown"}`);
  console.log("Cleanup recommendations:");
  for (const recommendation of health.cleanup_recommendations ?? ["compact", "dedupe", "prune"]) {
    console.log(`- ${recommendation}`);
  }
}
