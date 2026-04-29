from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request


API_URL = os.getenv("CODEX_MEM_API_URL", "http://127.0.0.1:8000").rstrip("/")
LIMIT = os.getenv("CODEX_MEM_INJECT_LIMIT", "5")
TOKEN_BUDGET = os.getenv("CODEX_MEM_TOKEN_BUDGET", "1200")
MIN_CAPTURE_CHARS = 80
MAX_CAPTURE_ITEMS = 3

WORKED_PATTERNS = [
    re.compile(r"\b(what worked|worked|passed|succeeded|verified|tests? pass(?:ed)?)\b", re.I),
    re.compile(r"\b(zadzialalo|powiodlo|przeszly|zweryfikowano)\b", re.I),
]

FAILED_PATTERNS = [
    re.compile(r"\b(what failed|failed|failure|error|broke|regression|not able|couldn't|cannot verify)\b", re.I),
    re.compile(r"\b(nie udalo|blad|awaria|regresja|nie moglem zweryfikowac)\b", re.I),
]

ACTION_PATTERNS = [
    re.compile(r"\b(add(?:ed)?|implement(?:ed)?|fix(?:ed)?|resolv(?:ed|e)|chang(?:ed|e)|update(?:d)?|wire(?:d)?|verify|verified|test(?:ed)?)\b", re.I),
    re.compile(r"\b(doda(?:łem|no)|zaimplementowa(?:łem|no)|naprawi(?:łem|ono)|rozwi(?:ązałem|ązano)|zmieni(?:łem|ono)|zweryfikowa(?:łem|no)|testy?)\b", re.I),
]

LOW_VALUE_PATTERNS = [
    re.compile(r"^\s*(ok|done|gotowe|jasne|pewnie|thanks|dzięki)[.!]?\s*$", re.I),
    re.compile(r"\b(nie udało|nie byłem w stanie|not able|couldn't|cannot verify|nie mogłem zweryfikować)\b", re.I),
]
EXTENDED_LOW_VALUE_PATTERNS = [
    re.compile(r"\b(i think|maybe|probably|guess|not sure|chyba|moze|prawdopodobnie)\b", re.I),
    re.compile(r"\b(debug log|temporary log|console\.log|print debugging|scratch)\b", re.I),
    re.compile(r"\b(created file|edited file|ran command|opened file)\b", re.I),
]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "user-prompt"
    payload = read_stdin_json()

    if mode == "stop":
        captured = capture_from_stop(payload)
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return

    if mode == "post-tool-use":
        capture_from_tool_result(payload)
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
    captured = capture_from_git_diff(payload)
    captured += capture_from_latest_commit(payload)
    if not message:
        return captured

    for memory in extract_memories(message):
        if post_memory(memory):
            captured += 1
    return captured


def capture_from_git_diff(payload: dict) -> int:
    cwd = payload.get("cwd") or os.getcwd()
    try:
        diff = subprocess.run(
            ["git", "diff", "--stat", "--", ":!data/db", ":!data/vectors"],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return 0
    stat = diff.stdout.strip()
    if diff.returncode != 0 or not stat:
        return 0
    memory = {
        "type": "fact",
        "title": "Working tree has code changes",
        "context": stat[:1200],
        "resolution": "Captured automatically from git diff --stat after a Codex turn.",
        "confidence": 0.6,
        "tags": ["auto-capture", "git-diff"],
        "source": "git-diff",
    }
    return 1 if post_memory(memory) else 0


def capture_from_latest_commit(payload: dict) -> int:
    cwd = payload.get("cwd") or os.getcwd()
    try:
        commit = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%h%n%s%n%b"],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return 0
    text = commit.stdout.strip()
    if commit.returncode != 0 or not text:
        return 0
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return 0
    commit_hash, subject = lines[0], lines[1]
    body = " ".join(lines[2:])
    memory = {
        "type": "fact",
        "title": f"Commit {commit_hash}: {subject}"[:120],
        "context": (body or subject)[:1200],
        "resolution": "Captured automatically from the latest git commit.",
        "confidence": 0.7,
        "tags": ["auto-capture", "git-commit"],
        "source": "git-commit",
    }
    return 1 if post_memory(memory) else 0


def capture_from_tool_result(payload: dict) -> int:
    failure = tool_failure_text(payload)
    if not failure:
        return 0

    memory = {
        "type": "bug",
        "title": title_from_text(failure),
        "context": failure[:1200],
        "resolution": "Captured automatically from a failed tool or runtime result.",
        "confidence": 0.7,
        "tags": ["auto-capture", "tool-error", "failed"],
        "source": "post-tool-use",
    }
    return 1 if post_memory(memory) else 0


def tool_failure_text(payload: dict) -> str:
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "tool").strip()
    exit_code = payload.get("exit_code")
    status = str(payload.get("status") or "").lower()
    error = payload.get("error") or payload.get("stderr") or payload.get("message")
    output = payload.get("output") or payload.get("stdout") or payload.get("result")
    text = extract_text(error) or extract_text(output)
    failed = bool(error) or status in {"error", "failed", "failure"} or (isinstance(exit_code, int) and exit_code != 0)
    if not failed or not text.strip():
        return ""
    return f"{tool_name} failed: {' '.join(text.split())}"


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
    seen_candidates = []
    for candidate in candidates:
        if len(candidate) < MIN_CAPTURE_CHARS or is_low_value(candidate):
            continue
        if not is_actionable_capture(candidate):
            continue
        if is_near_duplicate(candidate, seen_candidates):
            continue
        seen_candidates.append(candidate)
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
    if any(pattern.search(text) for pattern in FAILED_PATTERNS):
        return False
    return any(pattern.search(text) for pattern in LOW_VALUE_PATTERNS + EXTENDED_LOW_VALUE_PATTERNS)


def is_actionable_capture(text: str) -> bool:
    patterns = ACTION_PATTERNS + WORKED_PATTERNS + FAILED_PATTERNS
    return any(pattern.search(text) for pattern in patterns)


def is_near_duplicate(candidate: str, previous: list[str]) -> bool:
    candidate_tokens = token_set(candidate)
    if not candidate_tokens:
        return True
    for item in previous:
        tokens = token_set(item)
        overlap = len(candidate_tokens & tokens)
        union = len(candidate_tokens | tokens)
        if union and overlap / union >= 0.7:
            return True
    return False


def token_set(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_./:-]{3,}", text)}


def memory_payload(text: str) -> dict:
    memory_type = infer_memory_type(text)
    tags = ["auto-capture", "stop-hook"]
    if any(pattern.search(text) for pattern in WORKED_PATTERNS):
        tags.append("worked")
    if any(pattern.search(text) for pattern in FAILED_PATTERNS):
        tags.append("failed")
    return normalize_observation({
        "type": memory_type,
        "title": title_from_text(text),
        "context": text[:1200],
        "resolution": resolution_from_text(text),
        "confidence": 0.65,
        "tags": tags,
        "source": "stop-hook",
    })


def normalize_observation(memory: dict) -> dict:
    tags = []
    for tag in memory.get("tags", []):
        value = str(tag).strip().lower()
        if value and value not in tags:
            tags.append(value)
    normalized = {
        "type": memory.get("type") or "fact",
        "title": title_from_text(str(memory.get("title") or "Auto-captured Codex memory")),
        "context": " ".join(str(memory.get("context") or "").split())[:1200],
        "resolution": " ".join(str(memory.get("resolution") or "").split())[:1200],
        "confidence": float(memory.get("confidence") or 0.6),
        "tags": tags,
        "source": str(memory.get("source") or "auto-capture").strip()[:120],
    }
    normalized["confidence"] = max(0.0, min(normalized["confidence"], 1.0))
    return normalized


def infer_memory_type(text: str) -> str:
    lowered = text.lower()
    if any(pattern.search(text) for pattern in FAILED_PATTERNS):
        return "bug"
    if re.search(r"\b(fixed|resolved|naprawi|rozwiąza)\b", lowered):
        return "solution"
    if re.search(r"\b(decided|wybra|decyz)\b", lowered):
        return "decision"
    if re.search(r"\b(pattern|wzorzec|best practice)\b", lowered):
        return "pattern"
    return "solution"


def resolution_from_text(text: str) -> str:
    if any(pattern.search(text) for pattern in FAILED_PATTERNS):
        return "Captured automatically as a failed approach from the latest assistant response."
    if any(pattern.search(text) for pattern in WORKED_PATTERNS):
        return "Captured automatically as a working approach from the latest assistant response."
    return "Captured automatically from the latest assistant response."


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
