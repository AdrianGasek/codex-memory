import { MemoryClient } from "../client/memoryClient.js";

export async function explainMemoryCommand(args: string[]): Promise<void> {
  const id = args[0];
  if (!id) throw new Error("Usage: codex-memory explain-memory <memory-id>");
  const explanation = await new MemoryClient().explainMemory(id);
  console.log(`Memory: ${explanation.id}`);
  console.log(`Ranking reason: ${explanation.ranking_reason}`);
  console.log(`Matching query terms: ${explanation.matching_query_terms.join(", ") || "none"}`);
  console.log(`File/path evidence: ${explanation.file_path_evidence.join(", ") || "none"}`);
  console.log(`Usage evidence: ${explanation.usage_evidence.join(", ") || "none"}`);
  console.log(
    `Conflict/staleness signals: ${explanation.conflict_staleness_signals.join(", ") || "none"}`,
  );
}
