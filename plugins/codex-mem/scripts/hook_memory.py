from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request


API_URL = os.getenv("CODEX_MEM_API_URL", "http://127.0.0.1:8000").rstrip("/")
LIMIT = os.getenv("CODEX_MEM_INJECT_LIMIT", "5")
TOKEN_BUDGET = os.getenv("CODEX_MEM_TOKEN_BUDGET", "1200")
MIN_CAPTURE_CHARS = 80
MAX_CAPTURE_ITEMS = 3

ACTION_PATTERNS = [
    re.compile(r"\b(add(?:ed)?|implement(?:ed)?|fix(?:ed)?|resolv(?:ed|e)|chang(?:ed|e)|update(?:d)?|wire(?:d)?|verify|verified|test(?:ed)?)\b", re.I),
    re.compile(r"\b(doda(?:łem|no)|zaimplementowa(?:łem|no)|naprawi(?:łem|ono)|rozwi(?:ązałem|ązano)|zmieni(?:łem|ono)|zweryfikowa(?:łem|no)|testy?)\b", re.I),
]

LOW_VALUE_PATTERNS = [
    re.compile(r"^\s*(ok|done|gotowe|jasne|pewnie|thanks|dzięki)[.!]?\s*$", re.I),
    re.compile(r"\b(nie udało|nie byłem w stanie|not able|couldn't|cannot verify|nie mogłem zweryfikować)\b", re.I),
]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "user-prompt"
    payload = read_stdin_json()

    if mode == "stop":
        captured = capture_from_stop(payload)
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return

    query = payload.get("prompt") or payload.get("cwd") or "project memory"
    context = fetch_context(str(query))
    if not context:
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return

    if mode == "session-start":
        output = {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            },
        }
    else:
        output = {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            },
        }

    print(json.dumps(output))


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def fetch_context(query: str) -> str:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": LIMIT,
            "token_budget": TOKEN_BUDGET,
        }
    )
    request = urllib.request.Request(f"{API_URL}/memory/inject?{params}")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""
    return body.get("additional_context", "")


def capture_from_stop(payload: dict) -> int:
    message = latest_assistant_message(payload)
    if not message:
        return 0

    captured = 0
    for memory in extract_memories(message):
        if post_memory(memory):
            captured += 1
    return captured


def latest_assistant_message(payload: dict) -> str:
    direct = payload.get("last_assistant_message") or payload.get("assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    transcript_path = payload.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path.strip():
        return latest_assistant_message_from_transcript(Path(transcript_path))

    return ""


def latest_assistant_message_from_transcript(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    for line in reversed(lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("role") == "assistant":
            text = extract_text(event)
            if text:
                return text
        message = event.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            text = extract_text(message)
            if text:
                return text
    return ""


def extract_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (extract_text(item) for item in value) if part)
    if not isinstance(value, dict):
        return ""

    for key in ("text", "content", "output_text"):
        text = extract_text(value.get(key))
        if text:
            return text
    return ""


def extract_memories(message: str) -> list[dict]:
    cleaned = normalize_message(message)
    if len(cleaned) < MIN_CAPTURE_CHARS or is_low_value(cleaned):
        return []

    candidates = split_candidates(cleaned)
    memories = []
    for candidate in candidates:
        if len(candidate) < MIN_CAPTURE_CHARS or is_low_value(candidate):
            continue
        if not any(pattern.search(candidate) for pattern in ACTION_PATTERNS):
            continue
        memories.append(memory_payload(candidate))
        if len(memories) >= MAX_CAPTURE_ITEMS:
            break
    return memories


def normalize_message(message: str) -> str:
    lines = []
    in_fence = False
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        lines.append(line)
    return " ".join(lines)


def split_candidates(message: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZŁŚŻŹĆŃÓĄĘ])", message)
    grouped = []
    current = []
    for part in parts:
        current.append(part.strip())
        text = " ".join(current).strip()
        if len(text) >= MIN_CAPTURE_CHARS:
            grouped.append(text)
            current = []
    if current:
        tail = " ".join(current).strip()
        if grouped and len(tail) < MIN_CAPTURE_CHARS:
            grouped[-1] = f"{grouped[-1]} {tail}"
        elif tail:
            grouped.append(tail)
    return grouped or [message]


def is_low_value(text: str) -> bool:
    return any(pattern.search(text) for pattern in LOW_VALUE_PATTERNS)


def memory_payload(text: str) -> dict:
    memory_type = infer_memory_type(text)
    return {
        "type": memory_type,
        "title": title_from_text(text),
        "context": text[:1200],
        "resolution": "Captured automatically from the latest assistant response.",
        "confidence": 0.65,
        "tags": ["auto-capture", "stop-hook"],
        "source": "stop-hook",
    }


def infer_memory_type(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(fixed|resolved|naprawi|rozwiąza)\b", lowered):
        return "solution"
    if re.search(r"\b(decided|wybra|decyz)\b", lowered):
        return "decision"
    if re.search(r"\b(pattern|wzorzec|best practice)\b", lowered):
        return "pattern"
    return "solution"


def title_from_text(text: str) -> str:
    title = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    title = re.sub(r"\s+", " ", title).strip(" -")
    if len(title) > 120:
        title = title[:117].rstrip() + "..."
    return title or "Auto-captured Codex memory"


def post_memory(memory: dict) -> bool:
    body = json.dumps(memory).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}/memory",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


if __name__ == "__main__":
    main()
