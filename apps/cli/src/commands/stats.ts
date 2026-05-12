import { MemoryClient, type MemoryStats } from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

export async function statsCommand(args: string[] = []): Promise<void> {
  const options = parseOptions(args);
  const stats = await new MemoryClient().stats(
    option(options, "project") || undefined,
    option(options, "since") || undefined,
    options.has("impact"),
  );
  if (options.has("json")) {
    console.log(JSON.stringify(stats, null, 2));
    return;
  }
  printStats(stats);
}

function printStats(stats: MemoryStats): void {
  console.log("Memory stats");
  console.log(`Total injected memories: ${stats.total_injected_memories}`);
  console.log(`Average injected tokens: ${stats.average_injected_tokens}`);
  console.log(`Max injected tokens: ${stats.max_injected_tokens}`);
  console.log(`Skipped due to budget: ${stats.skipped_due_to_budget}`);
  console.log("Memory calls by command:");
  const entries = Object.entries(stats.calls_by_command);
  if (!entries.length) {
    console.log("- none");
  } else {
    for (const [command, count] of entries.sort(([left], [right]) =>
      left.localeCompare(right),
    )) {
      console.log(`- ${command}: ${count}`);
    }
  }
  console.log("Most recalled files:");
  if (!stats.most_recalled_files.length) {
    console.log("- none");
  } else {
    for (const item of stats.most_recalled_files) {
      console.log(`- ${item.file_path}: ${item.count}`);
    }
  }
  console.log("Most used memory types:");
  if (!stats.most_used_memory_types.length) {
    console.log("- none");
  } else {
    for (const item of stats.most_used_memory_types) {
      console.log(`- ${item.type}: ${item.count}`);
    }
  }
  if (stats.impact) {
    console.log("Impact:");
    console.log(
      `- memory-assisted sessions: ${stats.impact.memory_assisted_sessions}`,
    );
    console.log(`- boundary warnings: ${stats.impact.boundary_warnings}`);
    console.log(`- repeated bug reuse: ${stats.impact.repeated_bug_reuse}`);
    console.log(`- average context size: ${stats.impact.average_context_size}`);
  }
}
