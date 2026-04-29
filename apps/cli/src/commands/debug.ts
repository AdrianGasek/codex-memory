import { MemoryClient } from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

export async function debugCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const query = option(options, "query", "project memory");
  const limit = Number(option(options, "limit", "5"));
  const client = new MemoryClient();
  const health = await client.health();
  const injection = await client.inject(query, limit);

  console.log(`API: ${health.status}`);
  console.log("");
  console.log(injection || "No injection context available.");
}
