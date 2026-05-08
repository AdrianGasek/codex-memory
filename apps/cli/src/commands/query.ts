import { MemoryClient, type RetrievalProfile } from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

const profiles = new Set(["short", "normal", "deep"]);

export async function queryCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const query = option(options, "query") || (options.get("_") ?? []).join(" ");
  const limitOption = option(options, "limit");
  const limit = limitOption ? Number(limitOption) : undefined;
  const profileOption = option(options, "profile");
  if (profileOption && !profiles.has(profileOption)) {
    throw new Error('Invalid --profile. Use "short", "normal", or "deep".');
  }
  const profile = profileOption as RetrievalProfile | undefined;
  const path = option(options, "path") || undefined;
  const after = option(options, "after") || undefined;
  const before = option(options, "before") || undefined;
  const client = new MemoryClient();
  const results = await client.query(
    query,
    limit,
    path,
    after,
    before,
    profile,
  );

  if (results.length === 0) {
    console.log("No memory found.");
    return;
  }

  for (const result of results) {
    const entry = result.entry;
    console.log(`[${entry.type}] ${entry.title}`);
    console.log(
      `id=${entry.id} score=${result.score.toFixed(2)} confidence=${entry.confidence}`,
    );
    if (entry.context) console.log(`context: ${entry.context}`);
    if (entry.resolution) console.log(`resolution: ${entry.resolution}`);
    if (entry.file_paths.length)
      console.log(`files: ${entry.file_paths.join(", ")}`);
    if (entry.tags.length) console.log(`tags: ${entry.tags.join(", ")}`);
    console.log("");
  }
}
