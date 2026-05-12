export type MemoryType = "fact" | "decision" | "bug" | "solution" | "pattern";
export type RetrievalProfile = "short" | "normal" | "deep";

export interface MemoryPayload {
  type: MemoryType;
  title: string;
  context?: string;
  resolution?: string;
  confidence?: number;
  importance?: number;
  pinned?: boolean;
  file_paths?: string[];
  tags?: string[];
  source?: string;
  project?: string;
}

export type MemoryUpdatePayload = Partial<MemoryPayload>;

export interface MemoryEntry extends Required<Omit<MemoryPayload, "project">> {
  id: string;
  timestamp: string;
  project: string;
  status: "active" | "superseded" | "archived";
  conflict_ids: string[];
  superseded_by: string | null;
  retrieved_count: number;
  injected_count: number;
  last_used_timestamp: string | null;
}

export interface SearchResult {
  entry: MemoryEntry;
  score: number;
  reason: string;
}

export interface InjectionPreviewSelected {
  id: string;
  type: MemoryType;
  title: string;
  tokens: number;
  relevance: number;
  reason: string;
  mode: "full" | "summary";
  file_paths: string[];
  tags: string[];
  evidence?: string[];
}

export interface InjectionPreviewExcluded {
  id: string;
  type: MemoryType;
  title: string;
  tokens: number;
  relevance: number;
  reason: string;
  evidence?: string[];
}

export interface InjectionPreview {
  task: string;
  token_budget: number;
  candidate_count: number;
  selected_context: InjectionPreviewSelected[];
  excluded_context: InjectionPreviewExcluded[];
  selected_estimated_tokens: number;
  total_estimated_tokens: number;
  additional_context: string;
}

export interface ConfigDiagnostics {
  config_path: string;
  diagnostics: string[];
  debug_verbose: boolean;
  inject_limit: number;
  token_budget: number;
  vector_backend: string;
}

export interface MemoryStats {
  calls_by_command: Record<string, number>;
  total_injected_memories: number;
  average_injected_tokens: number;
  max_injected_tokens: number;
  skipped_due_to_budget: number;
  most_recalled_files: { file_path: string; count: number }[];
  most_used_memory_types: { type: MemoryType; count: number }[];
  impact?: {
    memory_assisted_sessions: number;
    boundary_warnings: number;
    repeated_bug_reuse: number;
    average_context_size: number;
  };
}

export interface MemoryExplanation {
  id: string;
  ranking_reason: string;
  matching_query_terms: string[];
  file_path_evidence: string[];
  usage_evidence: string[];
  conflict_staleness_signals: string[];
}

export interface MemoryHealth {
  status: string;
  components: { name: string; status: string; detail: string }[];
  config?: Record<string, unknown>;
  cleanup_recommendations?: string[];
  index_state?: string;
}

export class MemoryClient {
  private readonly apiUrl: string;

  constructor(
    apiUrl = process.env.CODEX_MEM_API_URL ?? "http://127.0.0.1:8000",
  ) {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  async health(): Promise<{ status: string }> {
    return this.request("/health");
  }

  async configDiagnostics(): Promise<ConfigDiagnostics> {
    return this.request("/memory/config/diagnostics");
  }

  async remember(payload: MemoryPayload): Promise<MemoryEntry> {
    return this.request("/memory", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async update(id: string, payload: MemoryUpdatePayload): Promise<MemoryEntry> {
    return this.request(`/memory/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async get(id: string): Promise<MemoryEntry> {
    return this.request(`/memory/${encodeURIComponent(id)}`);
  }

  async query(
    query: string,
    limit?: number,
    path?: string,
    after?: string,
    before?: string,
    profile?: RetrievalProfile,
  ): Promise<SearchResult[]> {
    const params = new URLSearchParams({ query });
    if (limit) params.set("limit", String(limit));
    if (path) params.set("path", path);
    if (after) params.set("after", after);
    if (before) params.set("before", before);
    if (profile) params.set("profile", profile);
    const response = await this.request<{ results: SearchResult[] }>(
      `/memory/search?${params}`,
    );
    return response.results;
  }

  async inject(
    query: string,
    limit?: number,
    profile?: RetrievalProfile,
  ): Promise<string> {
    const params = new URLSearchParams({ query });
    if (limit) params.set("limit", String(limit));
    if (profile) params.set("profile", profile);
    const response = await this.request<{ additional_context: string }>(
      `/memory/inject?${params}`,
    );
    return response.additional_context;
  }

  async injectPreview(
    query: string,
    limit?: number,
    profile?: RetrievalProfile,
    tokenBudget?: number,
  ): Promise<InjectionPreview> {
    const params = new URLSearchParams({ query });
    if (limit) params.set("limit", String(limit));
    if (profile) params.set("profile", profile);
    if (tokenBudget) params.set("token_budget", String(tokenBudget));
    return this.request(`/memory/inject-preview?${params}`);
  }

  async stats(
    project?: string,
    since?: string,
    impact?: boolean,
  ): Promise<MemoryStats> {
    const params = new URLSearchParams();
    if (project) params.set("project", project);
    if (since) params.set("since", since);
    if (impact) params.set("impact", "true");
    const suffix = params.size ? `?${params}` : "";
    return this.request(`/memory/stats${suffix}`);
  }

  async explainMemory(id: string): Promise<MemoryExplanation> {
    return this.request(`/memory/explain/${encodeURIComponent(id)}`);
  }

  async memoryHealth(): Promise<MemoryHealth> {
    return this.request("/memory/health/diagnostics");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.apiUrl}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(init.headers ?? {}),
      },
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Codex-Mem API ${response.status}: ${body}`);
    }

    return response.json() as Promise<T>;
  }
}
