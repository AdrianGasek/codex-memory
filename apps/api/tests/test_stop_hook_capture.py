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


def test_post_tool_use_captures_pr_review_feedback(monkeypatch):
    hook_memory = load_hook_module()
    posted = []

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory, "post_memory", fake_post)
    count = hook_memory.capture_from_tool_result(
        {
            "tool_name": "gh",
            "stdout": "Pull request review: requested changes on apps/api/app/main.py. Add validation before merge.",
        }
    )

    assert count == 1
    assert posted[0]["source"] == "git-pr-review"
    assert "review-feedback" in posted[0]["tags"]
    assert "requested changes" in posted[0]["context"]


def test_post_tool_use_captures_ci_build_and_test_failures(monkeypatch):
    hook_memory = load_hook_module()
    posted = []

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory, "post_memory", fake_post)
    count = hook_memory.capture_from_tool_result(
        {
            "tool_name": "github-actions",
            "status": "failed",
            "stdout": "Build failed: pytest apps/api/tests reported 2 test failures.",
        }
    )

    assert count == 1
    assert posted[0]["source"] == "ci-cd"
    assert "ci-cd" in posted[0]["tags"]
    assert "pytest apps/api/tests" in posted[0]["context"]


def test_post_tool_use_captures_runtime_log_errors(monkeypatch, tmp_path):
    hook_memory = load_hook_module()
    posted = []
    log_path = tmp_path / "logs" / "app.log"
    log_path.parent.mkdir()
    log_path.write_text("ERROR: RuntimeError: database connection failed\n", encoding="utf-8")

    def fake_post(memory):
        posted.append(memory)
        return True

    monkeypatch.setattr(hook_memory, "post_memory", fake_post)
    count = hook_memory.capture_from_tool_result({"log_path": str(log_path)})

    assert count == 1
    assert posted[0]["source"] == "runtime-log"
    assert "runtime-log" in posted[0]["tags"]
    assert "database connection failed" in posted[0]["context"]
    assert posted[0]["file_paths"] == [hook_memory.normalize_path(str(log_path))]


def test_runtime_log_capture_respects_no_store_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"no_store_paths": ["private"]}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()
    log_path = tmp_path / "private" / "app.log"
    log_path.parent.mkdir()
    log_path.write_text("ERROR: RuntimeError: private failure\n", encoding="utf-8")

    assert hook_memory.capture_from_tool_result({"log_path": str(log_path)}) == 0


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

    def fake_run(args, **kwargs):
        if args[:2] == ["git", "show"]:
            return SimpleNamespace(returncode=0, stdout="apps/api/app/storage/sqlite.py\nREADME.md\n")
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
    assert posted[0]["file_paths"] == ["apps/api/app/storage/sqlite.py", "readme.md"]


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


def test_auto_capture_annotates_detected_conflicts(monkeypatch):
    hook_memory = load_hook_module()

    monkeypatch.setattr(hook_memory, "find_capture_conflicts", lambda _memory: ["mem_old"])

    annotated = hook_memory.annotate_capture_conflicts(
        {
            "type": "decision",
            "title": "Use SQLite for memory storage",
            "context": "Later capture.",
            "resolution": "Keep SQLite.",
            "tags": ["auto-capture"],
            "source": "stop-hook",
        }
    )

    assert annotated["tags"] == ["auto-capture", "conflict", "latest-wins"]
    assert "mem_old" in annotated["resolution"]


def test_auto_capture_conflict_detection_respects_path_scope(monkeypatch):
    hook_memory = load_hook_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {
                            "entry": {
                                "id": "mem_api",
                                "title": "Use request validation",
                                "file_paths": ["apps/api/app/routes/memory.py"],
                            }
                        },
                        {
                            "entry": {
                                "id": "mem_cli",
                                "title": "Use request validation",
                                "file_paths": ["apps/cli/src/commands/remember.ts"],
                            }
                        },
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    conflicts = hook_memory.find_capture_conflicts(
        {
            "type": "decision",
            "title": "Use request validation",
            "file_paths": ["apps/api/app/routes/memory.py"],
        }
    )

    assert conflicts == ["mem_api"]


def test_approval_mode_queues_auto_capture_without_posting(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_MEM_CAPTURE_MODE", "approval")
    monkeypatch.chdir(tmp_path)
    hook_memory = load_hook_module()

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("approval mode should not post to the API")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", fail_urlopen)
    stored = hook_memory.post_memory(
        {
            "type": "solution",
            "title": "Capture requires approval",
            "context": "Auto-captured memory should wait for review.",
            "resolution": "Queue the payload before storing.",
            "tags": ["auto-capture"],
            "source": "stop-hook",
        }
    )

    queued = tmp_path / ".codex" / "PENDING_MEMORY.jsonl"
    body = json.loads(queued.read_text(encoding="utf-8").strip())

    assert stored is True
    assert body["status"] == "pending"
    assert body["memory"]["title"] == "Capture requires approval"


def test_passive_mode_collects_visible_suggestions_without_storing(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_MEM_CAPTURE_MODE", "passive")
    monkeypatch.chdir(tmp_path)
    hook_memory = load_hook_module()

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("passive mode should not post to the API")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", fail_urlopen)
    stored = hook_memory.post_memory(
        {
            "type": "solution",
            "title": "Capture can be suggested",
            "context": "Passive mode should show this without storage.",
            "resolution": "Collect the payload for hook output.",
            "tags": ["auto-capture"],
            "source": "stop-hook",
        }
    )

    summary = hook_memory.passive_capture_summary()

    assert stored is True
    assert not (tmp_path / ".codex" / "PENDING_MEMORY.jsonl").exists()
    assert "Codex-Mem passive capture suggestions:" in summary
    assert "[solution] Capture can be suggested (stop-hook)" in summary


def test_mode_config_supports_debug_and_overrides_capture_mode(monkeypatch):
    monkeypatch.setenv("CODEX_MEM_CAPTURE_MODE", "passive")
    monkeypatch.setenv("CODEX_MEM_MODE", "debug")
    hook_memory = load_hook_module()

    assert hook_memory.CAPTURE_MODE == "debug"
    assert hook_memory.debug_capture_summary("Stop", 2) == "Codex-Mem debug: mode=debug, hook=Stop, captured=2."


def test_mode_can_be_loaded_from_project_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"mode": "passive"}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.CAPTURE_MODE == "passive"


def test_debug_verbose_can_be_loaded_from_project_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"debug": {"verbose": True}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.DEBUG_VERBOSE is True
    assert hook_memory.debug_capture_summary("Stop", 2).endswith(
        "api=http://127.0.0.1:8000, limit=5, token_budget=1200."
    )


def test_debug_verbose_env_overrides_project_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_MEM_DEBUG_VERBOSE", "false")
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"debug": {"verbose": True}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.DEBUG_VERBOSE is False


def test_capture_debug_log_writes_jsonl_when_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps(
            {
                "debug": {
                    "capture_log_enabled": True,
                    "capture_log": ".codex/capture-debug.jsonl",
                }
            }
        ),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    written = hook_memory.write_capture_debug_event(
        "Stop",
        {"cwd": str(tmp_path), "tool_name": "test-tool"},
        captured=2,
    )

    log_path = tmp_path / ".codex" / "capture-debug.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert written is True
    assert event["hook"] == "Stop"
    assert event["captured"] == 2
    assert event["source"] == "test-tool"


def test_capture_debug_log_is_enabled_in_debug_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_MEM_MODE", "debug")
    monkeypatch.setenv("CODEX_MEM_CAPTURE_DEBUG_LOG", ".codex/debug-mode-capture.jsonl")
    hook_memory = load_hook_module()

    assert hook_memory.write_capture_debug_event("PostToolUse", {}, captured=1) is True
    assert (tmp_path / ".codex" / "debug-mode-capture.jsonl").exists()


def test_hook_enable_disable_settings(monkeypatch):
    monkeypatch.setenv("CODEX_MEM_DISABLED_HOOKS", "stop, userpromptsubmit")
    hook_memory = load_hook_module()

    assert hook_memory.hook_enabled("stop") is False
    assert hook_memory.hook_enabled("user-prompt") is False
    assert hook_memory.hook_enabled("post-tool-use") is True


def test_all_hooks_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CODEX_MEM_HOOKS_ENABLED", "false")
    hook_memory = load_hook_module()

    assert hook_memory.hook_enabled("session-start") is False
    assert hook_memory.hook_enabled("stop") is False


def test_startup_api_availability_check(monkeypatch):
    hook_memory = load_hook_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"status": "ok"}).encode("utf-8")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert hook_memory.api_available() is True


def test_startup_api_availability_check_fails_closed(monkeypatch):
    hook_memory = load_hook_module()

    def fail_urlopen(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", fail_urlopen)

    assert hook_memory.api_available() is False


def test_degraded_output_continues_without_injection():
    hook_memory = load_hook_module()

    output = hook_memory.degraded_output("offline")

    assert output == {
        "continue": True,
        "suppressOutput": True,
        "degraded": True,
        "message": "offline",
    }


def test_degraded_output_can_be_visible():
    hook_memory = load_hook_module()

    output = hook_memory.degraded_output("startup failed", visible=True)

    assert output["continue"] is True
    assert output["suppressOutput"] is False
    assert output["degraded"] is True


def test_debug_injection_summary_lists_injected_entries():
    hook_memory = load_hook_module()

    summary = hook_memory.debug_injection_summary(
        {
            "trace": {
                "requested_limit": 3,
                "candidate_count": 5,
                "injected_count": 1,
                "entries": [
                    {
                        "memory_id": "mem_123",
                        "title": "Use SQLite first",
                        "score": 4.2,
                        "reason": "title matched query",
                    }
                ],
            }
        }
    )

    assert "requested_limit=3 candidate_count=5 injected_count=1" in summary
    assert "Use SQLite first (mem_123, score=4.20): title matched query" in summary


def test_fetch_context_reads_additional_context(monkeypatch):
    hook_memory = load_hook_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"additional_context": "memory context"}).encode("utf-8")

    monkeypatch.setattr(hook_memory.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert hook_memory.fetch_context("storage") == "memory context"


def test_project_no_store_tags_skip_capture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"no_store_tags": ["private", "no-store"]}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.should_skip_memory({"tags": ["auto-capture", "private"]}) is True
    assert hook_memory.should_skip_memory({"tags": ["auto-capture"]}) is False


def test_project_no_store_paths_skip_capture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"no_store_paths": ["secrets", "*.pem", "private/*.md"]}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.should_skip_memory({"file_paths": ["secrets/token.txt"]}) is True
    assert hook_memory.should_skip_memory({"file_paths": ["keys/service.pem"]}) is True
    assert hook_memory.should_skip_memory({"file_paths": ["private/notes.md"]}) is True
    assert hook_memory.should_skip_memory({"file_paths": ["apps/api/app/main.py"]}) is False


def test_private_payload_tags_skip_response_capture(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"no_store_tags": ["private", "no-store"]}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    def fail_post(_memory):
        raise AssertionError("private payloads should not be stored")

    monkeypatch.setattr(hook_memory, "post_memory", fail_post)
    captured = hook_memory.capture_from_stop(
        {
            "tags": ["private"],
            "last_assistant_message": (
                "Implemented the private workflow capture path with tests. "
                "This would normally be actionable enough to store."
            ),
        }
    )

    assert captured == 0


def test_no_store_directive_skips_response_capture(monkeypatch):
    hook_memory = load_hook_module()

    def fail_post(_memory):
        raise AssertionError("no-store responses should not be stored")

    monkeypatch.setattr(hook_memory, "post_memory", fail_post)
    captured = hook_memory.capture_from_stop(
        {
            "last_assistant_message": (
                "[no-store] Implemented the private workflow capture path with tests. "
                "This would normally be actionable enough to store."
            ),
        }
    )

    assert captured == 0


def test_payload_tags_read_metadata_and_strings(monkeypatch):
    hook_memory = load_hook_module()

    assert hook_memory.is_no_store_payload({"metadata": {"tags": ["private"]}}) is True
    assert hook_memory.is_no_store_payload({"tags": "no-store,other"}) is True


def test_git_diff_capture_uses_configured_ignore_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"ignore_paths": ["logs", "*.log", "vendor"]}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.git_ignore_pathspecs() == [":!logs", ":!*.log", ":!vendor"]


def test_capture_sensitivity_controls_minimum_length(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps({"capture": {"sensitivity": "strict"}}),
        encoding="utf-8",
    )
    hook_memory = load_hook_module()

    assert hook_memory.capture_min_chars() == 140
