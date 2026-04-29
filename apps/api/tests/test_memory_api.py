import json

from fastapi.testclient import TestClient

from app.main import app
from app.core.models import MemoryCreate
from app.routes import memory
from app.storage.sqlite import MemoryStore


def test_memory_lifecycle(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    payload = {
        "type": "decision",
        "title": "Use SQLite first",
        "context": "MVP storage should be local and simple.",
        "resolution": "Semantic search can come later.",
        "confidence": 0.9,
        "tags": ["storage", "mvp"],
        "source": "test",
        "project": "tests",
    }
    created = client.post("/memory", json=payload)
    assert created.status_code == 200
    memory_id = created.json()["id"]

    search = client.get("/memory/search", params={"query": "SQLite", "limit": 5})
    assert search.status_code == 200
    assert search.json()["results"][0]["entry"]["id"] == memory_id
    assert search.json()["results"][0]["entry"]["retrieved_count"] == 1

    history = client.get("/memory/history", params={"memory_id": memory_id})
    assert history.status_code == 200
    assert history.json()[0]["action"] == "create"
    assert history.json()[0]["version"] == 1

    inject = client.get("/memory/inject", params={"query": "storage"})
    assert inject.status_code == 200
    injected = inject.json()
    assert "Relevant Codex-Mem Context" in injected["additional_context"]
    injected_entry = injected["results"][0]["entry"]
    assert injected_entry["retrieved_count"] == 2
    assert injected_entry["injected_count"] == 1
    assert injected_entry["last_used_timestamp"]
    assert injected["trace"]["injected_count"] == 1
    assert injected["trace"]["entries"][0]["memory_id"] == memory_id
    assert "matched" in injected["trace"]["entries"][0]["reason"]

    latest_trace = client.get("/memory/debug/injection")
    assert latest_trace.status_code == 200
    assert latest_trace.json()["id"] == injected["trace"]["id"]

    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    history = client.get("/memory/history", params={"memory_id": memory_id})
    assert history.status_code == 200
    assert [item["action"] for item in history.json()] == ["delete", "create"]


def test_memory_history_records_create_and_delete(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )

    entry = store.store(
        MemoryCreate(
            type="solution",
            title="Audit memory changes",
            context="Memory changes need a durable version trail.",
            resolution="Record immutable snapshots in memory_history.",
            confidence=0.85,
            tags=["audit"],
            source="test",
        )
    )

    created_history = store.history(memory_id=entry.id)
    assert len(created_history) == 1
    assert created_history[0].version == 1
    assert created_history[0].action == "create"
    assert created_history[0].snapshot.id == entry.id

    assert store.delete(entry.id) is True

    full_history = store.history(memory_id=entry.id)
    assert [item.action for item in full_history] == ["delete", "create"]
    assert [item.version for item in full_history] == [2, 1]

    exported = (tmp_path / ".codex" / "HISTORY.json").read_text(encoding="utf-8")
    assert "Audit memory changes" in exported


def test_conflicting_memory_uses_latest_wins_policy(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )

    old_entry = store.store(
        MemoryCreate(
            type="decision",
            title="Use SQLite for memory storage",
            context="Early MVP storage decision.",
            resolution="Keep memory in a local SQLite database.",
            confidence=0.8,
            tags=["storage"],
            source="test",
        )
    )
    new_entry = store.store(
        MemoryCreate(
            type="decision",
            title="Use SQLite for memory storage",
            context="Later decision with audit requirements.",
            resolution="Keep SQLite and add history/conflict metadata.",
            confidence=0.95,
            tags=["storage", "audit"],
            source="test",
        )
    )

    assert new_entry.conflict_ids == [old_entry.id]

    old_history = store.history(memory_id=old_entry.id)
    assert old_history[0].action == "supersede"
    assert old_history[0].snapshot.status == "superseded"
    assert old_history[0].snapshot.superseded_by == new_entry.id

    results = store.search(query="SQLite storage", limit=5, track_usage=False)
    assert [result.entry.id for result in results] == [new_entry.id]

    exported = json.loads((tmp_path / ".codex" / "INDEX.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in exported] == [new_entry.id]
    assert exported[0]["conflict_ids"] == [old_entry.id]


def test_file_path_scope_filters_search_and_limits_conflicts(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )

    api_entry = store.store(
        MemoryCreate(
            type="decision",
            title="Use request validation",
            context="API requests need validation.",
            resolution="Validate FastAPI payloads with Pydantic.",
            confidence=0.9,
            file_paths=["apps/api/app/routes/memory.py"],
            tags=["api"],
            source="test",
        )
    )
    cli_entry = store.store(
        MemoryCreate(
            type="decision",
            title="Use request validation",
            context="CLI arguments need validation.",
            resolution="Validate command flags before calling the API.",
            confidence=0.9,
            file_paths=["apps/cli/src/commands/remember.ts"],
            tags=["cli"],
            source="test",
        )
    )

    assert api_entry.status == "active"
    assert cli_entry.status == "active"
    assert cli_entry.conflict_ids == []

    api_results = store.search(query="validation", path="apps/api/app/routes/memory.py", track_usage=False)
    assert [result.entry.id for result in api_results] == [api_entry.id]

    cli_results = store.search(query="validation", path="apps/cli", track_usage=False)
    assert [result.entry.id for result in cli_results] == [cli_entry.id]

    exported = json.loads((tmp_path / ".codex" / "INDEX.json").read_text(encoding="utf-8"))
    exported_paths = {entry["id"]: entry["file_paths"] for entry in exported}
    assert exported_paths[api_entry.id] == ["apps/api/app/routes/memory.py"]
    assert exported_paths[cli_entry.id] == ["apps/cli/src/commands/remember.ts"]
