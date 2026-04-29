import { MemoryClient, type RetrievalProfile } from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

const profiles = new Set(["short", "normal", "deep"]);

export async function debugCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const query = option(options, "query", "project memory");
  const limitOption = option(options, "limit");
  const limit = limitOption ? Number(limitOption) : undefined;
  const profileOption = option(options, "profile");
  if (profileOption && !profiles.has(profileOption)) {
    throw new Error('Invalid --profile. Use "short", "normal", or "deep".');
  }
  const profile = profileOption as RetrievalProfile | undefined;
  const client = new MemoryClient();
  const health = await client.health();
  const injection = await client.inject(query, limit, profile);

  console.log(`API: ${health.status}`);
  console.log("");
  console.log(injection || "No injection context available.");
}
