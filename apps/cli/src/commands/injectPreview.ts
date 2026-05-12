import {
  MemoryClient,
  type InjectionPreview,
  type RetrievalProfile,
} from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

const profiles = new Set(["short", "normal", "deep"]);

export async function injectPreviewCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const positional = option(options, "_");
  const query = option(options, "query", positional || "project memory");
  const limitOption = option(options, "limit");
  const budgetOption = option(options, "budget");
  const profileOption = option(options, "profile");
  if (profileOption && !profiles.has(profileOption)) {
    throw new Error('Invalid --profile. Use "short", "normal", or "deep".');
  }
  const preview = await new MemoryClient().injectPreview(
    query,
    limitOption ? Number(limitOption) : undefined,
    profileOption as RetrievalProfile | undefined,
    budgetOption ? Number(budgetOption) : undefined,
  );

  if (options.has("json")) {
    console.log(JSON.stringify(toJsonPreview(preview), null, 2));
    return;
  }

  console.log(`Task: ${preview.task || "(empty)"}`);
  console.log(
    `Context budget: ${preview.token_budget} tokens; selected: ${preview.selected_estimated_tokens}; candidates: ${preview.candidate_count}`,
  );
  if (!preview.selected_context.length) {
    console.log("Selected context: none");
  } else {
    console.log("Selected context:");
    for (const item of preview.selected_context) {
      console.log(
        `- [${item.type}] ${item.title} (${item.tokens} tokens, score=${item.relevance.toFixed(2)}, ${item.mode})`,
      );
      console.log(`  ${item.reason}`);
    }
  }
  if (preview.excluded_context.length) {
    console.log("Excluded context:");
    for (const item of preview.excluded_context) {
      console.log(`- ${item.title}: ${item.reason}`);
    }
  }
}

function toJsonPreview(preview: InjectionPreview): unknown {
  return {
    task: preview.task,
    tokenBudget: preview.token_budget,
    candidateCount: preview.candidate_count,
    selectedContext: preview.selected_context.map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title,
      tokens: item.tokens,
      relevance: item.relevance,
      reason: item.reason,
      mode: item.mode,
      filePaths: item.file_paths,
      tags: item.tags,
    })),
    excludedContext: preview.excluded_context.map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title,
      tokens: item.tokens,
      relevance: item.relevance,
      reason: item.reason,
    })),
    selectedEstimatedTokens: preview.selected_estimated_tokens,
    totalEstimatedTokens: preview.total_estimated_tokens,
    additionalContext: preview.additional_context,
  };
}
