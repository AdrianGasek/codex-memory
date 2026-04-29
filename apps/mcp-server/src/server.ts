#!/usr/bin/env bun
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number;
  method: string;
  params?: Record<string, JsonValue>;
}

const apiUrl = (process.env.CODEX_MEM_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

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

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  drainBuffer().catch((error: unknown) => {
    writeError(null, error instanceof Error ? error.message : String(error));
  });
});

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
  if (request.id === undefined) return;

  try {
    switch (request.method) {
      case "initialize":
        writeResult(request.id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: "codex-mem", version: "0.1.0" }
        });
        return;
      case "tools/list":
        writeResult(request.id, { tools });
        return;
      case "tools/call":
        writeResult(request.id, await callTool(request.params ?? {}));
        return;
      default:
        writeError(request.id, `Unknown method: ${request.method}`, -32601);
    }
  } catch (error) {
    writeError(request.id, error instanceof Error ? error.message : String(error));
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
  writeMessage({ jsonrpc: "2.0", id, result });
}

function writeError(id: string | number | null, message: string, code = -32000): void {
  writeMessage({ jsonrpc: "2.0", id, error: { code, message } });
}

function writeMessage(payload: JsonValue): void {
  const body = JSON.stringify(payload);
  process.stdout.write(`Content-Length: ${Buffer.byteLength(body, "utf8")}\r\n\r\n${body}`);
}
