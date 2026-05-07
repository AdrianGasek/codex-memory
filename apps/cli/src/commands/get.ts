import { MemoryClient } from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

export async function getCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const id = option(options, "id") || (options.get("_") ?? [])[0];
  if (!id) {
    throw new Error("Missing memory id. Use get <id> or get --id <id>.");
  }

  const entry = await new MemoryClient().get(id);
  console.log(`[${entry.type}] ${entry.title}`);
  console.log(`id=${entry.id} confidence=${entry.confidence} importance=${entry.importance}`);
  if (entry.context) console.log(`context: ${entry.context}`);
  if (entry.resolution) console.log(`resolution: ${entry.resolution}`);
  if (entry.file_paths.length) console.log(`files: ${entry.file_paths.join(", ")}`);
  if (entry.tags.length) console.log(`tags: ${entry.tags.join(", ")}`);
}
