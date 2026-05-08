import { MemoryClient, type MemoryType } from "../client/memoryClient.js";
import { option, optionList, parseOptions } from "./args.js";

const allowedTypes = new Set([
  "fact",
  "decision",
  "bug",
  "solution",
  "pattern",
]);

export async function rememberCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const type = option(options, "type", "fact") as MemoryType;
  if (!allowedTypes.has(type)) {
    throw new Error(
      `Invalid --type "${type}". Use fact, decision, bug, solution, or pattern.`,
    );
  }

  const title = option(options, "title");
  if (!title) {
    throw new Error("Missing --title.");
  }

  const client = new MemoryClient();
  const entry = await client.remember({
    type,
    title,
    context: option(options, "context"),
    resolution: option(options, "resolution"),
    confidence: Number(option(options, "confidence", "0.75")),
    file_paths: optionList(options, "path"),
    tags: optionList(options, "tag"),
    source: option(options, "source", "cli"),
    project: option(options, "project") || undefined,
  });

  console.log(`Stored ${entry.id}: ${entry.title}`);
}
