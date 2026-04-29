import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "plugins" / "codex-mem" / "scripts" / "hook_memory.py"


def load_hook_module():
    spec = importlib.util.spec_from_file_location("hook_memory", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_stop_hook_extracts_actionable_memory():
    hook_memory = load_hook_module()

    message = (
        "Implemented the Stop hook extractor in plugins/codex-mem/scripts/hook_memory.py. "
        "It reads the latest assistant message, filters low-value responses, and stores "
        "validated implementation notes through the memory API."
    )

    memories = hook_memory.extract_memories(message)

    assert len(memories) == 1
    assert memories[0]["type"] == "solution"
    assert memories[0]["source"] == "stop-hook"
    assert "stop-hook" in memories[0]["tags"]
    assert "Stop hook extractor" in memories[0]["title"]


def test_stop_hook_ignores_low_value_message():
    hook_memory = load_hook_module()

    memories = hook_memory.extract_memories("Gotowe.")

    assert memories == []


def test_stop_hook_filters_guesses_logs_and_obvious_file_churn():
    hook_memory = load_hook_module()

    assert hook_memory.extract_memories(
        "I think maybe this fixed the issue, but I am not sure and need more debugging later."
    ) == []
    assert hook_memory.extract_memories(
        "Added console.log temporary log statements while debugging the command output path."
    ) == []
    assert hook_memory.extract_memories(
        "Created file apps/api/app/example.py and opened file apps/api/app/main.py during setup."
    ) == []


def test_stop_hook_reads_latest_assistant_message_from_transcript(tmp_path):
    hook_memory = load_hook_module()
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"role": "assistant", "content": "Older assistant response."}),
                json.dumps(
                    {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Fixed transcript fallback for Stop hook capture.",
                                }
                            ],
                        }
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    message = hook_memory.latest_assistant_message({"transcript_path": str(transcript)})

    assert message == "Fixed transcript fallback for Stop hook capture."


def test_stop_hook_posts_extracted_memory(monkeypatch):
    hook_memory = load_hook_module()
    posted = []

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory, "post_memory", fake_post)
    monkeypatch.setattr(hook_memory, "capture_from_git_diff", lambda _payload: 0)
    monkeypatch.setattr(hook_memory, "capture_from_latest_commit", lambda _payload: 0)

    count = hook_memory.capture_from_stop(
        {
            "last_assistant_message": (
                "Added automatic capture from the Codex Stop hook. "
                "The extractor stores concise implementation notes only when the response "
                "contains actionable work and enough detail to reuse later."
            )
        }
    )

    assert count == 1
    assert posted[0]["source"] == "stop-hook"


def test_stop_hook_captures_what_worked():
    hook_memory = load_hook_module()

    memories = hook_memory.extract_memories(
        "What worked: the smoke test passed after wiring semantic search through the "
        "local vector adapter, so future retrieval can reuse that implementation path."
    )

    assert len(memories) == 1
    assert memories[0]["type"] == "solution"
    assert "worked" in memories[0]["tags"]
    assert "working approach" in memories[0]["resolution"]


def test_stop_hook_captures_what_failed_as_bug():
    hook_memory = load_hook_module()

    memories = hook_memory.extract_memories(
        "What failed: npm could not run from PowerShell because script execution policy "
        "blocked npm.ps1, so validation needs npm.cmd or the repository smoke script."
    )

    assert len(memories) == 1
    assert memories[0]["type"] == "bug"
    assert "failed" in memories[0]["tags"]
    assert "failed approach" in memories[0]["resolution"]


def test_post_tool_use_captures_failed_tool_result(monkeypatch):
    hook_memory = load_hook_module()
    posted = []

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory, "post_memory", fake_post)

    count = hook_memory.capture_from_tool_result(
        {
            "tool_name": "shell_command",
            "exit_code": 1,
            "stderr": "npm.ps1 cannot be loaded because running scripts is disabled.",
        }
    )

    assert count == 1
    assert posted[0]["type"] == "bug"
    assert posted[0]["source"] == "post-tool-use"
    assert "tool-error" in posted[0]["tags"]
    assert "npm.ps1 cannot be loaded" in posted[0]["context"]


def test_stop_hook_captures_git_diff_stat(monkeypatch, tmp_path):
    hook_memory = load_hook_module()
    posted = []

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="apps/api/app/main.py | 2 ++\n1 file changed, 2 insertions(+)")

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory.subprocess, "run", fake_run)
    monkeypatch.setattr(hook_memory, "post_memory", fake_post)

    count = hook_memory.capture_from_git_diff({"cwd": str(tmp_path)})

    assert count == 1
    assert posted[0]["source"] == "git-diff"
    assert "git-diff" in posted[0]["tags"]
    assert "apps/api/app/main.py" in posted[0]["context"]


def test_stop_hook_captures_latest_commit(monkeypatch, tmp_path):
    hook_memory = load_hook_module()
    posted = []

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="abc1234\nAdd memory audit trail\nHistory is now exported.")

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory.subprocess, "run", fake_run)
    monkeypatch.setattr(hook_memory, "post_memory", fake_post)

    count = hook_memory.capture_from_latest_commit({"cwd": str(tmp_path)})

    assert count == 1
    assert posted[0]["source"] == "git-commit"
    assert "git-commit" in posted[0]["tags"]
    assert posted[0]["title"] == "Commit abc1234: Add memory audit trail"


def test_auto_capture_normalizes_observations():
    hook_memory = load_hook_module()

    normalized = hook_memory.normalize_observation(
        {
            "type": "solution",
            "title": "  Fixed noisy capture. Extra sentence ignored.  ",
            "context": "  repeated   whitespace   ",
            "resolution": "  works   now  ",
            "confidence": 2,
            "tags": ["Auto-Capture", "auto-capture", " Stop-Hook "],
            "source": " stop-hook ",
        }
    )

    assert normalized["title"] == "Fixed noisy capture."
    assert normalized["context"] == "repeated whitespace"
    assert normalized["resolution"] == "works now"
    assert normalized["confidence"] == 1.0
    assert normalized["tags"] == ["auto-capture", "stop-hook"]
    assert normalized["source"] == "stop-hook"


def test_stop_hook_drops_near_duplicate_candidates():
    hook_memory = load_hook_module()

    memories = hook_memory.extract_memories(
        "Implemented semantic search through a local vector adapter so retrieval can find related failures and solutions. "
        "Implemented semantic search through the local vector adapter so retrieval finds related failures and solutions."
    )

    assert len(memories) == 1
