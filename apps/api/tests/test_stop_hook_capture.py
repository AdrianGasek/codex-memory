import importlib.util
import json
from pathlib import Path


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
