import json
import os
import socket
import subprocess
import time
import urllib.request
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

    assert initialized["result"]["serverInfo"]["name"] == "codex-mem"
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
