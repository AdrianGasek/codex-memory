import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
from urllib.parse import parse_qs, urlparse
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "apps" / "mcp-server" / "fixtures" / "protocol"


def framed(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def read_message(process: subprocess.Popen) -> dict:
    assert process.stdout is not None
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = process.stdout.read(1)
        assert chunk, "MCP server closed stdout before sending a response"
        header += chunk
    header_text = header.decode("utf-8")
    length = int(header_text.lower().split("content-length:", 1)[1].split("\r\n", 1)[0].strip())
    body = process.stdout.read(length)
    return json.loads(body.decode("utf-8"))


class MemoryApiHandler(BaseHTTPRequestHandler):
    captured_requests: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        MemoryApiHandler.captured_requests.append({"path": self.path, "body": json.loads(body)})
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "id": "mem-mcp-store",
                    "type": "fact",
                    "title": "Stored through MCP",
                    "context": "MCP store call.",
                    "resolution": "",
                    "confidence": 0.75,
                    "importance": 0,
                    "pinned": False,
                    "file_paths": [],
                    "tags": [],
                    "source": "mcp",
                    "timestamp": "2026-05-06T00:00:00Z",
                    "project": "tests",
                    "status": "active",
                    "conflict_ids": [],
                    "superseded_by": None,
                    "retrieved_count": 0,
                    "injected_count": 0,
                    "last_used_timestamp": None,
                }
            ).encode("utf-8")
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        MemoryApiHandler.captured_requests.append({"path": parsed.path, "query": parse_qs(parsed.query)})
        if parsed.path == "/memory/search":
            payload = {
                "results": [
                    {
                        "entry": {"id": "mem-query", "type": "fact", "title": "Queried through MCP"},
                        "score": 1.0,
                        "reason": "matched query terms",
                    }
                ]
            }
        elif parsed.path == "/memory/history":
            payload = [{"memory_id": parse_qs(parsed.query).get("memory_id", [""])[0], "action": "create"}]
        elif parsed.path == "/memory/debug/injection":
            payload = {"id": "trace-1", "injected_count": 1}
        else:
            payload = {"id": parsed.path.rsplit("/", 1)[-1], "title": "Fetched through MCP"}
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_PATCH(self):
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        MemoryApiHandler.captured_requests.append({"path": self.path, "body": json.loads(body)})
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"id": self.path.rsplit("/", 1)[-1], "title": "Updated through MCP"}).encode("utf-8")
        )

    def do_DELETE(self):
        MemoryApiHandler.captured_requests.append({"path": self.path})
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"deleted": True}).encode("utf-8"))

    def log_message(self, format, *args):
        return


def test_mcp_server_initialize_and_tool_capabilities():
    initialize = json.loads((FIXTURE_DIR / "initialize.json").read_text(encoding="utf-8"))
    tools_list = json.loads((FIXTURE_DIR / "tools-list.json").read_text(encoding="utf-8"))

    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(framed(initialize))
        process.stdin.flush()
        initialized = read_message(process)

        process.stdin.write(framed(tools_list))
        process.stdin.flush()
        listed = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)

    assert initialized["result"]["serverInfo"]["name"] == "codex-memory"
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {
        "store_memory",
        "query_memory",
        "get_memory",
        "get_observations",
        "timeline",
        "update_memory",
        "debug_injection",
        "delete_memory",
    }.issubset(tool_names)


def test_mcp_server_http_transport_tools_list():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = {
        **os.environ,
        "CODEX_MEM_MCP_TRANSPORT": "http",
        "CODEX_MEM_MCP_HOST": "127.0.0.1",
        "CODEX_MEM_MCP_PORT": str(port),
    }
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        deadline = time.time() + 5
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    assert response.status == 200
                    break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.1)

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp",
            data=json.dumps(json.loads((FIXTURE_DIR / "tools-list.json").read_text(encoding="utf-8"))).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            listed = json.loads(response.read().decode("utf-8"))
    finally:
        process.terminate()
        process.wait(timeout=5)

    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "query_memory" in tool_names
    assert "debug_injection" in tool_names


def test_mcp_store_memory_tool_posts_to_api():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "store_memory",
                        "arguments": {
                            "type": "fact",
                            "title": "Stored through MCP",
                            "context": "MCP store call.",
                            "project": "tests",
                        },
                    },
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [
        {
            "path": "/memory",
            "body": {
                "source": "mcp",
                "confidence": 0.75,
                "type": "fact",
                "title": "Stored through MCP",
                "context": "MCP store call.",
                "project": "tests",
            },
        }
    ]
    content = response["result"]["content"][0]
    assert content["type"] == "text"
    assert json.loads(content["text"])["id"] == "mem-mcp-store"


def test_mcp_query_memory_tool_gets_search_results():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "query_memory",
                        "arguments": {
                            "query": "mcp query",
                            "limit": 3,
                            "type": "fact",
                            "project": "tests",
                            "path": "apps/mcp-server/src/server.ts",
                            "tags": ["mcp", "search"],
                        },
                    },
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [
        {
            "path": "/memory/search",
            "query": {
                "query": ["mcp query"],
                "limit": ["3"],
                "type": ["fact"],
                "project": ["tests"],
                "path": ["apps/mcp-server/src/server.ts"],
                "tags": ["mcp", "search"],
            },
        }
    ]
    content = response["result"]["content"][0]
    assert json.loads(content["text"])["results"][0]["entry"]["id"] == "mem-query"


def test_mcp_get_memory_tool_fetches_entry_by_id():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "get_memory", "arguments": {"id": "mem-get"}},
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [{"path": "/memory/mem-get", "query": {}}]
    assert json.loads(response["result"]["content"][0]["text"])["id"] == "mem-get"


def test_mcp_update_memory_tool_patches_entry():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "update_memory",
                        "arguments": {"id": "mem-update", "title": "Updated through MCP", "confidence": 0.9},
                    },
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [
        {"path": "/memory/mem-update", "body": {"title": "Updated through MCP", "confidence": 0.9}}
    ]
    assert json.loads(response["result"]["content"][0]["text"])["title"] == "Updated through MCP"


def test_mcp_delete_memory_tool_deletes_entry():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "delete_memory", "arguments": {"id": "mem-delete"}},
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [{"path": "/memory/mem-delete"}]
    assert json.loads(response["result"]["content"][0]["text"]) == {"deleted": True}


def test_mcp_timeline_tool_fetches_history_for_memory_id():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "timeline", "arguments": {"memory_id": "mem-time", "limit": 4}},
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [
        {"path": "/memory/history", "query": {"memory_id": ["mem-time"], "limit": ["4"]}}
    ]
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["memory_id"] == "mem-time"
    assert payload["history"][0]["action"] == "create"


def test_mcp_get_observations_tool_fetches_ids_in_batch():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {"name": "get_observations", "arguments": {"ids": ["mem-a", "mem-b"]}},
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [
        {"path": "/memory/mem-a", "query": {}},
        {"path": "/memory/mem-b", "query": {}},
    ]
    payload = json.loads(response["result"]["content"][0]["text"])
    assert [entry["id"] for entry in payload["observations"]] == ["mem-a", "mem-b"]


def test_mcp_debug_injection_tool_fetches_latest_trace():
    MemoryApiHandler.captured_requests = []
    server = HTTPServer(("127.0.0.1", 0), MemoryApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    env = {**os.environ, "CODEX_MEM_API_URL": f"http://127.0.0.1:{server.server_port}"}
    process = subprocess.Popen(
        ["bun", "run", "apps/mcp-server/src/server.ts"],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            framed(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {"name": "debug_injection", "arguments": {}},
                }
            )
        )
        process.stdin.flush()
        response = read_message(process)
    finally:
        process.terminate()
        process.wait(timeout=5)
        server.shutdown()
        server.server_close()

    assert MemoryApiHandler.captured_requests == [{"path": "/memory/debug/injection", "query": {}}]
    assert json.loads(response["result"]["content"][0]["text"])["id"] == "trace-1"
