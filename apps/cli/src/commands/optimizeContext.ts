import {
  MemoryClient,
  type InjectionPreview,
  type RetrievalProfile,
} from "../client/memoryClient.js";
import { option, parseOptions } from "./args.js";

type OptimizeStrategy = "minimal" | "balanced" | "deep" | "safety-first";

const strategies = new Set<OptimizeStrategy>([
  "minimal",
  "balanced",
  "deep",
  "safety-first",
]);

export async function optimizeContextCommand(args: string[]): Promise<void> {
  const options = parseOptions(args);
  const positional = option(options, "_");
  const query = option(options, "query", positional || "project memory");
  const budgetOption = option(options, "budget");
  const strategy = option(options, "strategy", "balanced");
  if (!isOptimizeStrategy(strategy)) {
    throw new Error(
      'Invalid --strategy. Use "minimal", "balanced", "deep", or "safety-first".',
    );
  }

  const preview = await new MemoryClient().injectPreview(
    query,
    undefined,
    strategyToProfile(strategy),
    budgetOption ? Number(budgetOption) : undefined,
  );

  if (options.has("json")) {
    console.log(JSON.stringify(toJsonOptimization(preview, strategy), null, 2));
    return;
  }

  console.log(`Task: ${preview.task || "(empty)"}`);
  console.log(`Strategy: ${strategy}`);
  const report = buildBudgetReport(preview);
  console.log(
    `Context budget: ${preview.token_budget} tokens; selected: ${preview.selected_estimated_tokens}; candidates: ${preview.candidate_count}`,
  );
  console.log(
    `Token report: selected=${report.selectedTokens}; skipped=${report.skippedTokens}; savedByDedupe=${report.savedByDedupeTokens}; staleSkips=${report.staleSkips}; conflicts=${report.conflicts}`,
  );
  const warning = budgetWarning(preview);
  if (warning) {
    console.log(`Budget warning: ${warning}`);
  }
  if (!preview.selected_context.length) {
    console.log("Selected context: none");
  } else {
    console.log("Selected context:");
    for (const [index, item] of preview.selected_context.entries()) {
      const classification = classifySelectedContext(item, index, strategy);
      console.log(
        `- [${classification}] [${item.type}] ${item.title} (${item.tokens} tokens, score=${item.relevance.toFixed(2)}, ${item.mode})`,
      );
      console.log(`  ${item.reason}`);
    }
  }
  if (preview.excluded_context.length) {
    console.log("Skipped context:");
    for (const item of preview.excluded_context) {
      console.log(`- ${item.title}: ${item.reason}`);
    }
  }
}

function isOptimizeStrategy(strategy: string): strategy is OptimizeStrategy {
  return strategies.has(strategy as OptimizeStrategy);
}

function strategyToProfile(strategy: OptimizeStrategy): RetrievalProfile {
  if (strategy === "minimal") return "short";
  if (strategy === "deep" || strategy === "safety-first") return "deep";
  return "normal";
}

function toJsonOptimization(
  preview: InjectionPreview,
  strategy: OptimizeStrategy,
): unknown {
  return {
    task: preview.task,
    strategy,
    tokenBudget: preview.token_budget,
    candidateCount: preview.candidate_count,
    budgetWarning: budgetWarning(preview),
    report: buildBudgetReport(preview),
    selectedContext: preview.selected_context.map((item, index) => ({
      id: item.id,
      type: item.type,
      title: item.title,
      classification: classifySelectedContext(item, index, strategy),
      tokens: item.tokens,
      relevance: item.relevance,
      reason: item.reason,
      mode: item.mode,
      filePaths: item.file_paths,
      tags: item.tags,
    })),
    skippedContext: preview.excluded_context.map((item) => ({
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

function budgetWarning(preview: InjectionPreview): string | null {
  if (preview.selected_estimated_tokens > preview.token_budget) {
    return `selected context is over budget by ${preview.selected_estimated_tokens - preview.token_budget} tokens`;
  }
  if (preview.selected_estimated_tokens >= preview.token_budget * 0.9) {
    return `selected context is within 10% of the ${preview.token_budget} token budget`;
  }
  return null;
}

function buildBudgetReport(preview: InjectionPreview): {
  selectedTokens: number;
  skippedTokens: number;
  savedByDedupeTokens: number;
  staleSkips: number;
  conflicts: number;
} {
  return {
    selectedTokens: preview.selected_estimated_tokens,
    skippedTokens: Math.max(
      0,
      preview.total_estimated_tokens - preview.selected_estimated_tokens,
    ),
    savedByDedupeTokens: dedupedSelectedTokens(preview),
    staleSkips: countReasonMatches(preview, "stale"),
    conflicts: countReasonMatches(preview, "conflict"),
  };
}

function dedupedSelectedTokens(preview: InjectionPreview): number {
  const seen = new Set<string>();
  let saved = 0;
  for (const item of preview.selected_context) {
    if (seen.has(item.id)) {
      saved += item.tokens;
    } else {
      seen.add(item.id);
    }
  }
  return saved;
}

function countReasonMatches(
  preview: InjectionPreview,
  needle: string,
): number {
  return preview.excluded_context.filter((item) =>
    item.reason.toLowerCase().includes(needle),
  ).length;
}

function classifySelectedContext(
  item: InjectionPreview["selected_context"][number],
  index: number,
  strategy: OptimizeStrategy,
): "must_include" | "nice_to_include" {
  if (strategy === "minimal") return "must_include";
  if (strategy === "safety-first" && ["bug", "decision", "solution"].includes(item.type)) {
    return "must_include";
  }
  if (index === 0 || item.relevance >= 0.85) return "must_include";
  return "nice_to_include";
}
