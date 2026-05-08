import {
  MemoryClient,
  type MemoryType,
  type MemoryUpdatePayload,
} from "../client/memoryClient.js";
import { option, optionList, parseOptions } from "./args.js";

const allowedTypes = new Set([
  "fact",
  "decision",
  "bug",
  "solution",
  "pattern",
]);

export async function updateCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const id = option(options, "id") || (options.get("_") ?? [])[0];
  if (!id) {
    throw new Error("Missing memory id. Use update <id> or update --id <id>.");
  }

  const payload: MemoryUpdatePayload = {};
  const type = option(options, "type");
  if (type) {
    if (!allowedTypes.has(type)) {
      throw new Error(
        `Invalid --type "${type}". Use fact, decision, bug, solution, or pattern.`,
      );
    }
    payload.type = type as MemoryType;
  }

  const title = option(options, "title");
  if (title) payload.title = title;
  const context = option(options, "context");
  if (context) payload.context = context;
  const resolution = option(options, "resolution");
  if (resolution) payload.resolution = resolution;
  const confidence = option(options, "confidence");
  if (confidence) payload.confidence = Number(confidence);
  const importance = option(options, "importance");
  if (importance) payload.importance = Number(importance);
  const pinned = option(options, "pinned");
  if (pinned)
    payload.pinned = ["1", "true", "yes", "on"].includes(pinned.toLowerCase());
  const filePaths = optionList(options, "path");
  if (filePaths.length > 0) payload.file_paths = filePaths;
  const tags = optionList(options, "tag");
  if (tags.length > 0) payload.tags = tags;
  const source = option(options, "source");
  if (source) payload.source = source;
  const project = option(options, "project");
  if (project) payload.project = project;

  if (Object.keys(payload).length === 0) {
    throw new Error("No update fields provided.");
  }

  const client = new MemoryClient();
  const entry = await client.update(id, payload);
  console.log(`Updated ${entry.id}: ${entry.title}`);
}
