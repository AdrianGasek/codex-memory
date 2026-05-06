from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


API_URL = os.getenv("CODEX_MEM_API_URL", "http://127.0.0.1:8000").rstrip("/")
LIMIT = os.getenv("CODEX_MEM_INJECT_LIMIT", "5")
TOKEN_BUDGET = os.getenv("CODEX_MEM_TOKEN_BUDGET", "1200")
SUPPORTED_MODES = {"active", "approval", "debug", "passive"}
APPROVAL_QUEUE = os.getenv("CODEX_MEM_APPROVAL_QUEUE", ".codex/PENDING_MEMORY.jsonl")
HOOKS_ENABLED = os.getenv("CODEX_MEM_HOOKS_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
DISABLED_HOOKS = {
    hook_name.strip().lower()
    for hook_name in os.getenv("CODEX_MEM_DISABLED_HOOKS", "").split(",")
    if hook_name.strip()
}
MIN_CAPTURE_CHARS = 80
MAX_CAPTURE_ITEMS = 3
PASSIVE_SUGGESTIONS: list[dict] = []
PROJECT_CONFIG = {}


def project_config() -> dict:
    global PROJECT_CONFIG
    if PROJECT_CONFIG:
        return PROJECT_CONFIG
    path = Path.cwd() / ".codex" / "mem.config.json"
    try:
        PROJECT_CONFIG = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        PROJECT_CONFIG = {}
    return PROJECT_CONFIG


def configured_capture_mode() -> str:
    capture_config = project_config().get("capture", {})
    config_mode = capture_config.get("mode") if isinstance(capture_config, dict) else None
    mode = os.getenv("CODEX_MEM_MODE", os.getenv("CODEX_MEM_CAPTURE_MODE", str(config_mode or "active"))).strip().lower()
    if mode not in SUPPORTED_MODES:
        return "active"
    return mode


def config_bool(env_name: str, fallback: bool) -> bool:
    value = os.getenv(env_name)
    if value is None:
        return fallback
    return value.strip().lower() in {"1", "true", "yes", "on"}


def configured_debug_verbose() -> bool:
    debug_config = project_config().get("debug", {})
    fallback = bool(debug_config.get("verbose", False)) if isinstance(debug_config, dict) else False
    return config_bool("CODEX_MEM_DEBUG_VERBOSE", fallback)


def configured_capture_debug_log_enabled() -> bool:
    debug_config = project_config().get("debug", {})
    fallback = bool(debug_config.get("capture_log_enabled", False)) if isinstance(debug_config, dict) else False
    return config_bool("CODEX_MEM_CAPTURE_DEBUG_LOG_ENABLED", fallback)


def configured_capture_debug_log_path() -> str:
    debug_config = project_config().get("debug", {})
    fallback = ".codex/CAPTURE_DEBUG.jsonl"
    if isinstance(debug_config, dict) and debug_config.get("capture_log"):
        fallback = str(debug_config["capture_log"])
    return os.getenv("CODEX_MEM_CAPTURE_DEBUG_LOG", fallback)


CAPTURE_MODE = configured_capture_mode()
DEBUG_VERBOSE = configured_debug_verbose()
CAPTURE_DEBUG_LOG_ENABLED = configured_capture_debug_log_enabled()
CAPTURE_DEBUG_LOG = configured_capture_debug_log_path()
HOOK_ALLOW_EXTERNAL_PATHS = config_bool("CODEX_MEM_HOOK_ALLOW_EXTERNAL_PATHS", False)

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


def resolve_hook_path(raw_path: str | Path) -> Path | None:
    base = Path.cwd().resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if HOOK_ALLOW_EXTERNAL_PATHS or resolved == base or resolved.is_relative_to(base):
        return resolved
    return None


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "user-prompt"
    payload = read_stdin_json()

    if not hook_enabled(mode):
        print(json.dumps({"continue": True, "suppressOutput": True}))
        return

    if mode == "session-start" and not api_available():
        print(json.dumps(degraded_output(f"Codex-Mem API is unavailable at {API_URL}; memory startup check failed.", visible=True)))
        return

    if mode == "stop":
        captured = capture_from_stop(payload)
        write_capture_debug_event("Stop", payload, captured)
        output = {"continue": True, "suppressOutput": CAPTURE_MODE not in {"debug", "passive"}}
        if CAPTURE_MODE == "passive" and captured:
            output["message"] = passive_capture_summary()
        if CAPTURE_MODE == "debug":
            output["message"] = debug_capture_summary("Stop", captured)
        print(json.dumps(output))
        return

    if mode == "post-tool-use":
        captured = capture_from_tool_result(payload)
        write_capture_debug_event("PostToolUse", payload, captured)
        output = {"continue": True, "suppressOutput": CAPTURE_MODE not in {"debug", "passive"}}
        if CAPTURE_MODE == "passive" and captured:
            output["message"] = passive_capture_summary()
        if CAPTURE_MODE == "debug":
            output["message"] = debug_capture_summary("PostToolUse", captured)
        print(json.dumps(output))
        return

    query = payload.get("prompt") or payload.get("cwd") or "project memory"
    if is_no_store_payload(payload) or has_no_store_directive(str(query)):
        print(json.dumps(degraded_output("Codex-Mem skipped memory lookup for a private/no-store prompt.")))
        return
    injection = fetch_injection(str(query))
    context = injection.get("additional_context", "")
    if not context:
        print(json.dumps(degraded_output("Codex-Mem memory context was unavailable; continuing without injection.")))
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

    if CAPTURE_MODE == "debug":
        output["suppressOutput"] = False
        output["message"] = debug_injection_summary(injection)

    print(json.dumps(output))


def degraded_output(message: str, visible: bool = False) -> dict:
    return {
        "continue": True,
        "suppressOutput": not visible,
        "degraded": True,
        "message": message,
    }


def write_capture_debug_event(hook_name: str, payload: dict, captured: int) -> bool:
    if not (CAPTURE_DEBUG_LOG_ENABLED or CAPTURE_MODE == "debug"):
        return False
    log_path = Path(CAPTURE_DEBUG_LOG)
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hook": hook_name,
        "mode": CAPTURE_MODE,
        "captured": captured,
        "cwd": payload.get("cwd") or os.getcwd(),
        "source": payload.get("tool_name") or payload.get("tool") or "assistant",
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        return False
    return True


def hook_enabled(mode: str) -> bool:
    if not HOOKS_ENABLED:
        return False
    normalized = mode.strip().lower()
    aliases = {
        "session-start": "sessionstart",
        "user-prompt": "userpromptsubmit",
        "post-tool-use": "posttooluse",
    }
    candidates = {normalized, aliases.get(normalized, normalized)}
    return not candidates.intersection(DISABLED_HOOKS)


def read_stdin_json() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def fetch_context(query: str) -> str:
    return fetch_injection(query).get("additional_context", "")


def fetch_injection(query: str) -> dict:
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
        return {}
    return body


def api_available() -> bool:
    request = urllib.request.Request(f"{API_URL}/health")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            if not 200 <= response.status < 300:
                return False
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return body.get("status") == "ok"


def capture_from_stop(payload: dict) -> int:
    message = latest_assistant_message(payload)
    if is_no_store_payload(payload) or has_no_store_directive(message):
        return 0
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
            ["git", "diff", "--stat", "--", *git_ignore_pathspecs()],
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
    file_paths = latest_commit_file_paths(cwd)
    memory = {
        "type": "fact",
        "title": f"Commit {commit_hash}: {subject}"[:120],
        "context": (body or subject)[:1200],
        "resolution": "Captured automatically from the latest git commit.",
        "confidence": 0.7,
        "file_paths": file_paths,
        "tags": ["auto-capture", "git-commit"],
        "source": "git-commit",
    }
    return 1 if post_memory(memory) else 0


def latest_commit_file_paths(cwd: str) -> list[str]:
    try:
        changed = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    if changed.returncode != 0:
        return []
    return [normalize_path(line) for line in changed.stdout.splitlines() if line.strip()]


def capture_from_tool_result(payload: dict) -> int:
    if is_no_store_payload(payload):
        return 0
    review_feedback = pr_review_feedback_text(payload)
    if review_feedback:
        memory = {
            "type": "fact",
            "title": title_from_text(review_feedback),
            "context": review_feedback[:1200],
            "resolution": "Captured automatically from PR or review feedback in tool output.",
            "confidence": 0.7,
            "tags": ["auto-capture", "git-pr-review", "review-feedback"],
            "source": "git-pr-review",
        }
        return 1 if post_memory(memory) else 0

    ci_failure = ci_failure_text(payload)
    if ci_failure:
        memory = {
            "type": "bug",
            "title": title_from_text(ci_failure),
            "context": ci_failure[:1200],
            "resolution": "Captured automatically from CI/CD, build, or test failure output.",
            "confidence": 0.75,
            "tags": ["auto-capture", "ci-cd", "build-failure", "failed"],
            "source": "ci-cd",
        }
        return 1 if post_memory(memory) else 0

    runtime_log = runtime_log_text(payload)
    if runtime_log:
        log_path = str(payload.get("log_path") or payload.get("runtime_log_path") or "").strip()
        memory = {
            "type": "bug",
            "title": title_from_text(runtime_log),
            "context": runtime_log[:1200],
            "resolution": "Captured automatically from runtime log output.",
            "confidence": 0.7,
            "file_paths": [normalize_path(log_path)] if log_path else [],
            "tags": ["auto-capture", "runtime-log", "failed"],
            "source": "runtime-log",
        }
        return 1 if post_memory(memory) else 0

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


def pr_review_feedback_text(payload: dict) -> str:
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "").lower()
    text = extract_text(payload.get("output") or payload.get("stdout") or payload.get("result") or payload.get("message"))
    if not text.strip():
        return ""
    lowered = text.lower()
    tool_mentions_pr = any(marker in tool_name for marker in ("gh", "github", "pr", "pull"))
    feedback_markers = ("pull request", "review", "requested changes", "review comment", "inline comment")
    if not tool_mentions_pr and not any(marker in lowered for marker in feedback_markers):
        return ""
    if not any(marker in lowered for marker in feedback_markers):
        return ""
    return f"PR review feedback: {' '.join(text.split())}"


def ci_failure_text(payload: dict) -> str:
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "").lower()
    status = str(payload.get("status") or "").lower()
    exit_code = payload.get("exit_code")
    text = extract_text(payload.get("error") or payload.get("stderr") or payload.get("output") or payload.get("stdout"))
    if not text.strip():
        return ""
    failed = bool(payload.get("error") or payload.get("stderr")) or status in {"error", "failed", "failure"} or (
        isinstance(exit_code, int) and exit_code != 0
    )
    lowered = f"{tool_name} {text}".lower()
    ci_markers = ("ci", "github actions", "workflow", "build", "pytest", "test failed", "tests failed", "npm test")
    if failed and any(marker in lowered for marker in ci_markers):
        return f"CI/CD failure: {' '.join(text.split())}"
    return ""


def runtime_log_text(payload: dict) -> str:
    log_path = str(payload.get("log_path") or payload.get("runtime_log_path") or "").strip()
    if log_path and is_no_store_path(log_path):
        return ""
    text = extract_text(payload.get("runtime_log") or payload.get("log") or "")
    if not text and log_path:
        path = resolve_hook_path(log_path)
        if not path:
            return ""
        try:
            text = path.read_text(encoding="utf-8")[:4000]
        except OSError:
            return ""
    if not text.strip():
        return ""
    lowered = text.lower()
    markers = ("traceback", "exception", "fatal", "runtimeerror", "error:")
    if not any(marker in lowered for marker in markers):
        return ""
    return f"Runtime log failure: {' '.join(text.split())}"


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
        path = resolve_hook_path(transcript_path)
        return latest_assistant_message_from_transcript(path) if path else ""

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
    min_chars = capture_min_chars()
    if len(cleaned) < min_chars or is_low_value(cleaned):
        return []

    candidates = split_candidates(cleaned)
    memories = []
    seen_candidates = []
    for candidate in candidates:
        if len(candidate) < min_chars or is_low_value(candidate):
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


def capture_min_chars() -> int:
    sensitivity = str(project_config().get("capture", {}).get("sensitivity", "standard")).lower()
    if sensitivity == "high":
        return 40
    if sensitivity == "strict":
        return 140
    return MIN_CAPTURE_CHARS


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
    annotated = annotate_capture_conflicts(memory)
    if should_skip_memory(annotated):
        return False
    if CAPTURE_MODE == "passive":
        PASSIVE_SUGGESTIONS.append(annotated)
        return True

    if CAPTURE_MODE == "approval":
        return queue_capture_for_approval(annotated)

    body = json.dumps(annotated).encode("utf-8")
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


def should_skip_memory(memory: dict) -> bool:
    no_store_tags = configured_no_store_tags()
    memory_tags = {str(tag).lower() for tag in memory.get("tags", [])}
    if no_store_tags.intersection(memory_tags):
        return True
    return any(is_no_store_path(path) for path in memory.get("file_paths", []) or [])


def configured_no_store_tags() -> set[str]:
    capture_config = project_config().get("capture", {})
    configured = capture_config.get("no_store_tags", ["private", "no-store"])
    return {str(tag).strip().lower() for tag in configured if str(tag).strip()}


def payload_tags(payload: dict) -> set[str]:
    raw_tags = payload.get("tags") or payload.get("memory_tags") or []
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[\s,]+", raw_tags)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        raw_tags = list(raw_tags) + list(metadata.get("tags") or [])
    return {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()}


def is_no_store_payload(payload: dict) -> bool:
    return bool(payload_tags(payload).intersection(configured_no_store_tags()))


def has_no_store_directive(text: str) -> bool:
    if not text:
        return False
    tags = configured_no_store_tags()
    lowered = text.lower()
    return any(f"#{tag}" in lowered or f"[{tag}]" in lowered for tag in tags)


def configured_no_store_paths() -> list[str]:
    capture_config = project_config().get("capture", {})
    configured = capture_config.get("no_store_paths", [])
    return [normalize_path(str(path)) for path in configured if str(path).strip()]


def is_no_store_path(path: str) -> bool:
    normalized = normalize_path(path)
    for pattern in configured_no_store_paths():
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if normalized == pattern or normalized.startswith(f"{pattern}/"):
            return True
        if f"/{pattern}/" in normalized:
            return True
    return False


def git_ignore_pathspecs() -> list[str]:
    capture_config = project_config().get("capture", {})
    ignore_paths = capture_config.get("ignore_paths", ["data/db", "data/vectors"])
    return [f":!{str(path).strip()}" for path in ignore_paths if str(path).strip()]


def queue_capture_for_approval(memory: dict) -> bool:
    queue_path = Path(APPROVAL_QUEUE)
    if not queue_path.is_absolute():
        queue_path = Path.cwd() / queue_path
    try:
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"status": "pending", "memory": memory}, sort_keys=True) + "\n")
        return True
    except OSError:
        return False


def passive_capture_summary() -> str:
    lines = ["Codex-Mem passive capture suggestions:"]
    for memory in PASSIVE_SUGGESTIONS:
        memory_type = str(memory.get("type") or "fact")
        title = str(memory.get("title") or "Untitled memory")
        source = str(memory.get("source") or "auto-capture")
        lines.append(f"- [{memory_type}] {title} ({source})")
    return "\n".join(lines)


def debug_capture_summary(hook_name: str, captured: int) -> str:
    summary = f"Codex-Mem debug: mode={CAPTURE_MODE}, hook={hook_name}, captured={captured}."
    if not DEBUG_VERBOSE:
        return summary
    return f"{summary} api={API_URL}, limit={LIMIT}, token_budget={TOKEN_BUDGET}."


def debug_injection_summary(injection: dict) -> str:
    trace = injection.get("trace") or {}
    entries = trace.get("entries") or []
    lines = [
        "Codex-Mem debug: injected memory entries:",
        f"- requested_limit={trace.get('requested_limit', 0)} candidate_count={trace.get('candidate_count', 0)} injected_count={trace.get('injected_count', len(entries))}",
    ]
    if DEBUG_VERBOSE:
        lines.append(f"- api={API_URL} limit={LIMIT} token_budget={TOKEN_BUDGET}")
    if not entries:
        lines.append("- no entries injected")
        return "\n".join(lines)
    for entry in entries:
        title = str(entry.get("title") or "Untitled memory")
        memory_id = str(entry.get("memory_id") or "")
        score = entry.get("score", 0)
        reason = str(entry.get("reason") or "no ranking reason")
        lines.append(f"- {title} ({memory_id}, score={float(score):.2f}): {reason}")
    return "\n".join(lines)


def annotate_capture_conflicts(memory: dict) -> dict:
    conflict_ids = find_capture_conflicts(memory)
    if not conflict_ids:
        return memory

    annotated = dict(memory)
    tags = list(annotated.get("tags") or [])
    for tag in ("conflict", "latest-wins"):
        if tag not in tags:
            tags.append(tag)
    annotated["tags"] = tags

    resolution = str(annotated.get("resolution") or "").strip()
    conflict_note = f"Auto-capture detected conflicting active memory IDs before storing: {', '.join(conflict_ids)}."
    annotated["resolution"] = " ".join(part for part in (resolution, conflict_note) if part)[:1200]
    return annotated


def find_capture_conflicts(memory: dict) -> list[str]:
    title = str(memory.get("title") or "").strip()
    memory_type = str(memory.get("type") or "").strip()
    if not title or not memory_type:
        return []

    params = {
        "query": title,
        "type": memory_type,
        "limit": "10",
    }
    project = str(memory.get("project") or "").strip()
    if project:
        params["project"] = project

    file_paths = [str(path) for path in memory.get("file_paths") or [] if str(path).strip()]
    if file_paths:
        params["path"] = file_paths[0]

    request = urllib.request.Request(f"{API_URL}/memory/search?{urllib.parse.urlencode(params)}")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    conflicts = []
    entry_key = conflict_key(title)
    for result in body.get("results", []):
        entry = result.get("entry", {})
        if conflict_key(str(entry.get("title") or "")) != entry_key:
            continue
        if not scopes_overlap([str(path) for path in entry.get("file_paths") or []], file_paths):
            continue
        entry_id = str(entry.get("id") or "").strip()
        if entry_id:
            conflicts.append(entry_id)
    return conflicts


def conflict_key(value: str) -> str:
    return " ".join(part.strip(".,;!?()[]{}'\"`").lower() for part in value.split())


def scopes_overlap(existing_paths: list[str], new_paths: list[str]) -> bool:
    if not existing_paths or not new_paths:
        return True
    normalized_existing = [normalize_path(path) for path in existing_paths]
    for path in new_paths:
        requested = normalize_path(path)
        for existing in normalized_existing:
            if existing == requested or existing.startswith(f"{requested}/") or requested.startswith(f"{existing}/"):
                return True
    return False


def normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/").strip("/").lower()


if __name__ == "__main__":
    main()
