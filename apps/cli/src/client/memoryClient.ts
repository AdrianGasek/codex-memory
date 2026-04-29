export type MemoryType = "fact" | "decision" | "bug" | "solution" | "pattern";

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

export interface MemoryEntry extends Required<Omit<MemoryPayload, "project">> {
  id: string;
  timestamp: string;
  project: string;
  status: "active" | "superseded";
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

  async query(query: string, limit = 10, path?: string): Promise<SearchResult[]> {
    const params = new URLSearchParams({ query, limit: String(limit) });
    if (path) params.set("path", path);
    const response = await this.request<{ results: SearchResult[] }>(`/memory/search?${params}`);
    return response.results;
  }

  async inject(query: string, limit = 5): Promise<string> {
    const params = new URLSearchParams({ query, limit: String(limit) });
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
