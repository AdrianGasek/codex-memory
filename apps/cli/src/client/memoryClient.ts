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

export class MemoryClient {
  private readonly apiUrl: string;

  constructor(apiUrl = process.env.CODEX_MEM_API_URL ?? "http://127.0.0.1:8000") {
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  async health(): Promise<{ status: string }> {
    return this.request("/health");
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
    const response = await this.request<{ results: SearchResult[] }>(`/memory/search?${params}`);
    return response.results;
  }

  async inject(query: string, limit?: number, profile?: RetrievalProfile): Promise<string> {
    const params = new URLSearchParams({ query });
    if (limit) params.set("limit", String(limit));
    if (profile) params.set("profile", profile);
    const response = await this.request<{ additional_context: string }>(`/memory/inject?${params}`);
    return response.additional_context;
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
