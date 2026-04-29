import json

from fastapi.testclient import TestClient

from app.main import app
from app.core.models import MemoryCreate
from app.routes import memory
from app.storage.sqlite import MemoryStore
from app.storage.vector import ChromaVectorStore, PgVectorStore, create_vector_store


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


def test_memory_update_endpoint_records_auditable_version(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    client = TestClient(app)
    created = client.post(
        "/memory",
        json={
            "type": "fact",
            "title": "Ranking is keyword only",
            "context": "Initial implementation note.",
            "resolution": "Replace later.",
            "confidence": 0.5,
            "tags": ["ranking"],
            "source": "test",
            "project": "tests",
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    updated = client.patch(
        f"/memory/{memory_id}",
        json={
            "type": "decision",
            "title": "Ranking uses hybrid scoring",
            "resolution": "Combine keyword, recency, confidence, importance, and usage signals.",
            "confidence": 0.9,
            "importance": 0.8,
            "tags": ["ranking", "audit"],
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == memory_id
    assert body["type"] == "decision"
    assert body["title"] == "Ranking uses hybrid scoring"
    assert body["tags"] == ["ranking", "audit"]

    history = client.get("/memory/history", params={"memory_id": memory_id})
    assert history.status_code == 200
    assert [item["action"] for item in history.json()] == ["update", "create"]
    assert [item["version"] for item in history.json()] == [2, 1]

    exported = json.loads((tmp_path / ".codex" / "INDEX.json").read_text(encoding="utf-8"))
    assert exported[0]["title"] == "Ranking uses hybrid scoring"


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


def test_search_filters_by_created_date_range(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    old_entry = store.store(
        MemoryCreate(
            type="fact",
            title="Old ranking note",
            context="Ranking started with keywords.",
            source="test",
        )
    )
    new_entry = store.store(
        MemoryCreate(
            type="fact",
            title="New ranking note",
            context="Ranking now includes recency.",
            source="test",
        )
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE memories SET timestamp = ? WHERE id = ?",
            ("2026-01-01T00:00:00+00:00", old_entry.id),
        )
        conn.execute(
            "UPDATE memories SET timestamp = ? WHERE id = ?",
            ("2026-04-01T00:00:00+00:00", new_entry.id),
        )

    client = TestClient(app)
    response = client.get(
        "/memory/search",
        params={
            "query": "ranking",
            "after": "2026-03-01T00:00:00Z",
            "before": "2026-04-30T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert [result["entry"]["id"] for result in response.json()["results"]] == [new_entry.id]

    invalid = client.get("/memory/search", params={"after": "not-a-date"})
    assert invalid.status_code == 400


def test_search_and_injection_support_retrieval_profiles(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    for index in range(5):
        store.store(
            MemoryCreate(
                type="fact",
                title=f"Profile memory {index}",
                context="Shared profile query text.",
                source="test",
            )
        )

    client = TestClient(app)
    short = client.get("/memory/search", params={"query": "profile", "profile": "short"})
    assert short.status_code == 200
    assert len(short.json()["results"]) == 3

    explicit_limit = client.get(
        "/memory/search",
        params={"query": "profile", "profile": "deep", "limit": 4},
    )
    assert explicit_limit.status_code == 200
    assert len(explicit_limit.json()["results"]) == 4

    injection = client.get("/memory/inject", params={"query": "profile", "profile": "short"})
    assert injection.status_code == 200
    assert injection.json()["trace"]["requested_limit"] == 3


def test_search_uses_semantic_embedding_similarity(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="bug",
            title="Runtime error capture",
            context="Tool output exceptions should be stored for later diagnosis.",
            resolution="Record failures with source and command context.",
            source="test",
        )
    )

    results = store.search(query="failure diagnosis", limit=3, track_usage=False)

    assert results[0].entry.id == entry.id
    assert "semantic embedding similarity" in results[0].reason


def test_memory_store_uses_vector_store_adapter(tmp_path):
    class FakeVectorStore:
        def __init__(self):
            self.embedded_texts = []

        def embed(self, text: str) -> list[float]:
            self.embedded_texts.append(text)
            if "query" in text:
                return [1.0, 0.0]
            return [0.9, 0.1]

        def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
            return 0.95

    vector_store = FakeVectorStore()
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=vector_store,
    )
    entry = store.store(
        MemoryCreate(
            type="fact",
            title="Adapter-backed memory",
            context="Stored through an injected vector store.",
            source="test",
        )
    )

    results = store.search(query="query with no lexical overlap", track_usage=False)

    assert results[0].entry.id == entry.id
    assert any("Adapter-backed memory" in text for text in vector_store.embedded_texts)
    assert vector_store.embedded_texts[-1] == "query with no lexical overlap"


def test_optional_vector_backends_are_selectable():
    chroma = create_vector_store("chroma", chroma_url="http://chroma.local")
    pgvector = create_vector_store("pgvector", pgvector_dsn="postgresql://memory")

    assert isinstance(chroma, ChromaVectorStore)
    assert chroma.url == "http://chroma.local"
    assert isinstance(pgvector, PgVectorStore)
    assert pgvector.dsn == "postgresql://memory"


def test_injection_summarizes_memories_when_budget_is_tight(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    for index in range(3):
        store.store(
            MemoryCreate(
                type="solution",
                title=f"Budget memory {index}",
                context=("budget " + "detail " * 120).strip(),
                resolution=("Use a compact summary when retrieved memory exceeds budget. " * 20).strip(),
                source="test",
            )
        )

    additional_context, _results, trace = store.inject_context(query="budget", limit=3, token_budget=100)

    assert "# Summarized Memory" in additional_context
    assert "Use a compact summary" in additional_context
    assert trace.injected_count >= 1
    assert len(additional_context) <= 450


def test_progressive_disclosure_index_and_get_by_id(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Use compact index first",
            context="Progressive disclosure should keep initial retrieval small.",
            resolution="Return compact search results first and fetch full details by ID.",
            tags=["retrieval"],
            source="test",
        )
    )

    client = TestClient(app)
    index = client.get("/memory/index", params={"query": "compact retrieval"})
    assert index.status_code == 200
    compact = index.json()["results"][0]
    assert compact["id"] == entry.id
    assert compact["title"] == "Use compact index first"
    assert "context" not in compact
    assert "resolution" not in compact

    full = client.get(f"/memory/{entry.id}")
    assert full.status_code == 200
    assert full.json()["context"] == "Progressive disclosure should keep initial retrieval small."
