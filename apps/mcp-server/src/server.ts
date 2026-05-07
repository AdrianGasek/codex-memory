#!/usr/bin/env bun
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number;
  method: string;
  params?: Record<string, JsonValue>;
}

declare const Bun: {
  serve: (options: {
    hostname: string;
    port: number;
    fetch: (request: Request) => Response | Promise<Response>;
  }) => unknown;
};

const apiUrl = (process.env.CODEX_MEM_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const transport = (process.env.CODEX_MEM_MCP_TRANSPORT ?? "stdio").toLowerCase();
const httpHost = process.env.CODEX_MEM_MCP_HOST ?? "127.0.0.1";
const httpPort = Number(process.env.CODEX_MEM_MCP_PORT ?? 3333);

const tools: JsonValue[] = [
  {
    name: "store_memory",
    description: "Store a structured Codex-Mem memory entry.",
    inputSchema: {
      type: "object",
      required: ["type", "title"],
      properties: {
        type: { type: "string", enum: ["fact", "decision", "bug", "solution", "pattern"] },
        title: { type: "string" },
        context: { type: "string" },
        resolution: { type: "string" },
        confidence: { type: "number", minimum: 0, maximum: 1 },
        file_paths: { type: "array", items: { type: "string" } },
        tags: { type: "array", items: { type: "string" } },
        source: { type: "string" },
        project: { type: "string" }
      }
    }
  },
  {
    name: "query_memory",
    description: "Query Codex-Mem entries with keyword search.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        limit: { type: "number", minimum: 1, maximum: 50 },
        type: { type: "string" },
        project: { type: "string" },
        path: { type: "string" },
        tags: { type: "array", items: { type: "string" } }
      }
    }
  },
  {
    name: "get_memory",
    description: "Fetch a full Codex-Mem entry by id.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string" }
      }
    }
  },
  {
    name: "timeline",
    description: "Fetch memory history around a memory id or around entries matching a query.",
    inputSchema: {
      type: "object",
      properties: {
        memory_id: { type: "string" },
        query: { type: "string" },
        limit: { type: "number", minimum: 1, maximum: 25 }
      }
    }
  },
  {
    name: "get_observations",
    description: "Fetch full memory observations for a batch of memory ids.",
    inputSchema: {
      type: "object",
      required: ["ids"],
      properties: {
        ids: { type: "array", items: { type: "string" }, minItems: 1, maxItems: 25 }
      }
    }
  },
  {
    name: "update_memory",
    description: "Update an existing Codex-Mem entry by id.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string" },
        type: { type: "string", enum: ["fact", "decision", "bug", "solution", "pattern"] },
        title: { type: "string" },
        context: { type: "string" },
        resolution: { type: "string" },
        confidence: { type: "number", minimum: 0, maximum: 1 },
        importance: { type: "number", minimum: 0, maximum: 1 },
        pinned: { type: "boolean" },
        file_paths: { type: "array", items: { type: "string" } },
        tags: { type: "array", items: { type: "string" } },
        source: { type: "string" },
        project: { type: "string" }
      }
    }
  },
  {
    name: "debug_injection",
    description: "Fetch the latest Codex-Mem injection debug trace.",
    inputSchema: {
      type: "object",
      properties: {}
    }
  },
  {
    name: "delete_memory",
    description: "Delete a Codex-Mem entry by id.",
    inputSchema: {
      type: "object",
      required: ["id"],
      properties: {
        id: { type: "string" }
      }
    }
  }
];

let buffer = "";

if (transport === "http") {
  startHttpServer();
} else {
  startStdioServer();
}

function startStdioServer(): void {
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    buffer += chunk;
    drainBuffer().catch((error: unknown) => {
      writeError(null, error instanceof Error ? error.message : String(error));
    });
  });
}

function startHttpServer(): void {
  Bun.serve({
    hostname: httpHost,
    port: httpPort,
    async fetch(request: Request): Promise<Response> {
      const url = new URL(request.url);
      if (request.method === "GET" && url.pathname === "/health") {
        return Response.json({ status: "ok", transport: "http" });
      }
      if (request.method !== "POST" || url.pathname !== "/mcp") {
        return Response.json({ error: "Not found" }, { status: 404 });
      }
      const payload = await request.json() as JsonRpcRequest;
      const response = await dispatchMessage(payload);
      return Response.json(response ?? {});
    }
  });
}

async function drainBuffer(): Promise<void> {
  while (true) {
    const headerEnd = buffer.indexOf("\r\n\r\n");
    if (headerEnd === -1) return;

    const header = buffer.slice(0, headerEnd);
    const match = /Content-Length:\s*(\d+)/i.exec(header);
    if (!match) {
      buffer = "";
      throw new Error("Missing Content-Length header.");
    }

    const length = Number(match[1]);
    const bodyStart = headerEnd + 4;
    if (buffer.length < bodyStart + length) return;

    const body = buffer.slice(bodyStart, bodyStart + length);
    buffer = buffer.slice(bodyStart + length);
    await handleMessage(JSON.parse(body) as JsonRpcRequest);
  }
}

async function handleMessage(request: JsonRpcRequest): Promise<void> {
  const response = await dispatchMessage(request);
  if (response) writeMessage(response);
}

async function dispatchMessage(request: JsonRpcRequest): Promise<JsonValue | null> {
  if (request.id === undefined) return null;

  try {
    switch (request.method) {
      case "initialize":
        return rpcResult(request.id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: "codex-memory", version: "0.1.0" }
        });
      case "tools/list":
        return rpcResult(request.id, { tools });
      case "tools/call":
        return rpcResult(request.id, await callTool(request.params ?? {}));
      default:
        return rpcError(request.id, `Unknown method: ${request.method}`, -32601);
    }
  } catch (error) {
    return rpcError(request.id, error instanceof Error ? error.message : String(error));
  }
}

async function callTool(params: Record<string, JsonValue>): Promise<JsonValue> {
  const name = String(params.name ?? "");
  const args = (params.arguments ?? {}) as Record<string, JsonValue>;

  switch (name) {
    case "store_memory": {
      const entry = await apiRequest("/memory", {
        method: "POST",
        body: JSON.stringify({ source: "mcp", confidence: 0.75, ...args })
      });
      return toolText(JSON.stringify(entry, null, 2));
    }
    case "query_memory": {
      const query = String(args.query ?? "");
      const limit = Number(args.limit ?? 10);
      const searchParams = new URLSearchParams({ query, limit: String(limit) });
      if (typeof args.type === "string") searchParams.set("type", args.type);
      if (typeof args.project === "string") searchParams.set("project", args.project);
      if (typeof args.path === "string") searchParams.set("path", args.path);
      if (Array.isArray(args.tags)) {
        for (const tag of args.tags) searchParams.append("tags", String(tag));
      }
      const results = await apiRequest(`/memory/search?${searchParams}`);
      return toolText(JSON.stringify(results, null, 2));
    }
    case "get_memory": {
      const id = String(args.id ?? "");
      if (!id) throw new Error("get_memory requires id.");
      const entry = await apiRequest(`/memory/${encodeURIComponent(id)}`);
      return toolText(JSON.stringify(entry, null, 2));
    }
    case "timeline": {
      const memoryId = String(args.memory_id ?? "");
      const query = String(args.query ?? "");
      const limit = Number(args.limit ?? 10);
      if (memoryId) {
        const searchParams = new URLSearchParams({ memory_id: memoryId, limit: String(limit) });
        const history = await apiRequest(`/memory/history?${searchParams}`);
        return toolText(JSON.stringify({ memory_id: memoryId, history }, null, 2));
      }
      if (!query) throw new Error("timeline requires memory_id or query.");

      const searchParams = new URLSearchParams({ query, limit: String(Math.min(limit, 5)) });
      const search = await apiRequest(`/memory/search?${searchParams}`) as { results?: { entry?: { id?: string; title?: string } }[] };
      const entries = await Promise.all(
        (search.results ?? []).map(async (result) => {
          const entry = result.entry ?? {};
          const id = String(entry.id ?? "");
          const historyParams = new URLSearchParams({ memory_id: id, limit: String(limit) });
          const history = id ? await apiRequest(`/memory/history?${historyParams}`) : [];
          return { memory_id: id, title: entry.title ?? "", history };
        })
      );
      return toolText(JSON.stringify({ query, entries }, null, 2));
    }
    case "get_observations": {
      if (!Array.isArray(args.ids) || args.ids.length === 0) {
        throw new Error("get_observations requires ids.");
      }
      const ids = args.ids.map((id) => String(id)).filter(Boolean).slice(0, 25);
      const observations = await Promise.all(
        ids.map((id) => apiRequest(`/memory/${encodeURIComponent(id)}`))
      );
      return toolText(JSON.stringify({ observations }, null, 2));
    }
    case "update_memory": {
      const id = String(args.id ?? "");
      if (!id) throw new Error("update_memory requires id.");
      const { id: _id, ...payload } = args;
      const entry = await apiRequest(`/memory/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      return toolText(JSON.stringify(entry, null, 2));
    }
    case "debug_injection": {
      const trace = await apiRequest("/memory/debug/injection");
      return toolText(JSON.stringify(trace, null, 2));
    }
    case "delete_memory": {
      const id = String(args.id ?? "");
      if (!id) throw new Error("delete_memory requires id.");
      const result = await apiRequest(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
      return toolText(JSON.stringify(result, null, 2));
    }
    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

async function apiRequest(path: string, init: RequestInit = {}): Promise<JsonValue> {
  const response = await fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init.headers ?? {})
    }
  });
  if (!response.ok) {
    throw new Error(`Codex-Mem API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<JsonValue>;
}

function toolText(text: string): JsonValue {
  return { content: [{ type: "text", text }] };
}

function writeResult(id: string | number, result: JsonValue): void {
  writeMessage(rpcResult(id, result));
}

function writeError(id: string | number | null, message: string, code = -32000): void {
  writeMessage(rpcError(id, message, code));
}

function rpcResult(id: string | number, result: JsonValue): JsonValue {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(id: string | number | null, message: string, code = -32000): JsonValue {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function writeMessage(payload: JsonValue): void {
  const body = JSON.stringify(payload);
  process.stdout.write(`Content-Length: ${Buffer.byteLength(body, "utf8")}\r\n\r\n${body}`);
}
