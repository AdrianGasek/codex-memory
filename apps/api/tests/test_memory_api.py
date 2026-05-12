import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.models import MemoryCreate, MemoryUpdate
from app.routes import memory
from app.storage import sqlite as sqlite_storage
from app.storage.sqlite import MemoryStore
from app.storage.vector import (
    ChromaVectorStore,
    LocalVectorStore,
    PgVectorStore,
    VectorBackendUnavailable,
    VectorRecord,
    VectorSearchResult,
    create_vector_store,
)


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
    assert "full context injected" in injected["trace"]["entries"][0]["reason"]

    latest_trace = client.get("/memory/debug/injection")
    assert latest_trace.status_code == 200
    assert latest_trace.json()["id"] == injected["trace"]["id"]

    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    history = client.get("/memory/history", params={"memory_id": memory_id})
    assert history.status_code == 200
    assert [item["action"] for item in history.json()] == ["delete", "create"]


def test_memory_reuse_across_store_instances_without_copy_paste(tmp_path):
    db_path = tmp_path / "db" / "codex-mem.sqlite3"
    codex_dir = tmp_path / ".codex"
    first_session = MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")
    decision = first_session.store(
        MemoryCreate(
            type="decision",
            title="Use SQLite for durable memory",
            context="Session one chose SQLite persistence.",
            resolution="Future sessions should retrieve this instead of restating it manually.",
            source="test",
        )
    )

    second_session = MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")
    context, results, trace = second_session.inject_context(query="durable memory persistence", limit=3, token_budget=500)

    assert results[0].entry.id == decision.id
    assert "Use SQLite for durable memory" in context
    assert trace.entries[0].memory_id == decision.id


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


def test_secret_redaction_covers_common_token_formats(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="bug",
            title="Leaked credentials were found",
            context=(
                "AWS key AKIAABCDEFGHIJKLMNOP and GitHub token "
                "ghp_abcdefghijklmnopqrstuvwxyzABCDE plus bearer "
                "Bearer abcdefghijklmnopqrstuvwxyz1234567890 should be hidden."
            ),
            resolution=(
                "Private key -----BEGIN PRIVATE KEY-----\n"
                "abcdefghijklmnopqrstuvwxyz\n"
                "-----END PRIVATE KEY----- was removed."
            ),
            source="test",
        )
    )

    combined = f"{entry.title} {entry.context} {entry.resolution}"
    assert "AKIAABCDEFGHIJKLMNOP" not in combined
    assert "ghp_abcdefghijklmnopqrstuvwxyzABCDE" not in combined
    assert "Bearer abcdefghijklmnopqrstuvwxyz1234567890" not in combined
    assert "BEGIN PRIVATE KEY" not in combined
    assert combined.count("[REDACTED]") >= 4


def test_raw_sqlite_storage_does_not_contain_secret_values(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    store.store(
        MemoryCreate(
            type="bug",
            title="Secret storage regression",
            context="Never persist token=super-secret-token-value or sk-abcdefghijklmnopqrstuvwxyz123456.",
            resolution="Redact before insert, export, and history recording.",
            source="test",
        )
    )

    raw_db = (tmp_path / "db" / "codex-mem.sqlite3").read_bytes()
    exported = (tmp_path / ".codex" / "MEMORY.md").read_text(encoding="utf-8")
    history = (tmp_path / ".codex" / "HISTORY.json").read_text(encoding="utf-8")
    assert b"super-secret-token-value" not in raw_db
    assert b"sk-abcdefghijklmnopqrstuvwxyz123456" not in raw_db
    assert "super-secret-token-value" not in exported
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in history


def test_redaction_applies_to_exports_history_audit_and_traces(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="bug",
            title="Trace secret",
            context="Secret token=trace-secret-value should be hidden.",
            resolution="Redaction covers exports and traces.",
            source="test",
        )
    )
    store.update(entry.id, MemoryUpdate(context="Updated token=updated-secret-value should be hidden."))
    store.inject_context(query="Find token=query-secret-value", limit=1, token_budget=500)

    raw_db = (tmp_path / "db" / "codex-mem.sqlite3").read_bytes()
    exported_files = [
        tmp_path / ".codex" / "MEMORY.md",
        tmp_path / ".codex" / "INDEX.json",
        tmp_path / ".codex" / "HISTORY.json",
        tmp_path / ".codex" / "AUDIT.json",
    ]
    exported_text = "\n".join(path.read_text(encoding="utf-8") for path in exported_files)
    trace = store.latest_injection_trace()

    assert b"trace-secret-value" not in raw_db
    assert b"updated-secret-value" not in raw_db
    assert b"query-secret-value" not in raw_db
    assert "trace-secret-value" not in exported_text
    assert "updated-secret-value" not in exported_text
    assert trace is not None
    assert "query-secret-value" not in trace.query


def test_redaction_failure_masks_fields_instead_of_storing_raw_text(tmp_path, monkeypatch):
    class BrokenPattern:
        def sub(self, _replacement, _value):
            raise RuntimeError("redactor failed")

    monkeypatch.setattr(sqlite_storage, "SECRET_PATTERNS", [BrokenPattern()])
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="fact",
            title="Sensitive title",
            context="Sensitive context",
            resolution="Sensitive resolution",
            source="test",
        )
    )

    raw_db = (tmp_path / "db" / "codex-mem.sqlite3").read_bytes()
    assert entry.title == "[REDACTED]"
    assert entry.context == "[REDACTED]"
    assert entry.resolution == "[REDACTED]"
    assert b"Sensitive context" not in raw_db


def test_pii_redaction_masks_email_phone_and_ssn(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="fact",
            title="User contact details should be removed",
            context="Contact ada@example.com or +1 (202) 555-0199 before using SSN 123-45-6789.",
            resolution="Keep only the non-sensitive implementation note.",
            source="test",
        )
    )

    assert "ada@example.com" not in entry.context
    assert "+1 (202) 555-0199" not in entry.context
    assert "123-45-6789" not in entry.context
    assert entry.context.count("[REDACTED]") == 3


def test_pii_redaction_keeps_common_technical_identifiers(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    entry = store.store(
        MemoryCreate(
            type="fact",
            title="Technical identifiers",
            context="Keep HTTP 404, port 127.0.0.1:8000, file apps/api/app/main.py, and version 1.2.3.",
            resolution="These values are operational metadata, not PII.",
            source="test",
        )
    )

    assert "HTTP 404" in entry.context
    assert "127.0.0.1:8000" in entry.context
    assert "apps/api/app/main.py" in entry.context
    assert "1.2.3" in entry.context


def test_local_db_encryption_option_protects_text_fields(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        encryption_key="test encryption key",
    )
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Encrypt local memory",
            context="Plaintext context should not be visible in SQLite.",
            resolution="Decrypt when reading through MemoryStore.",
            source="test",
        )
    )
    updated = store.update(entry.id, MemoryUpdate(title="Encrypted edit"))
    assert updated is not None
    store.inject_context(query="Plaintext context", limit=1, token_budget=500)
    store.delete(entry.id)

    with sqlite3.connect(tmp_path / "db" / "codex-mem.sqlite3") as conn:
        raw_history = conn.execute("SELECT snapshot FROM memory_history ORDER BY version LIMIT 1").fetchone()[0]
        raw_audit = conn.execute("SELECT title FROM memory_audit ORDER BY timestamp LIMIT 1").fetchone()[0]
        raw_trace = conn.execute("SELECT entries FROM injection_traces ORDER BY timestamp LIMIT 1").fetchone()[0]

    raw_db = (tmp_path / "db" / "codex-mem.sqlite3").read_bytes()
    assert b"Plaintext context should not be visible" not in raw_db
    assert b"Encrypt local memory" not in raw_db
    assert raw_history.startswith("enc:v2:")
    assert raw_audit.startswith("enc:v2:")
    assert raw_trace.startswith("enc:v2:")
    assert store.history(memory_id=entry.id)[-1].snapshot.context == "Plaintext context should not be visible in SQLite."
    assert store.audit_log(memory_id=entry.id)[0].title == "Encrypted edit"
    assert store.latest_injection_trace() is not None
    assert store.latest_injection_trace().entries[0].title == "Encrypted edit"


def test_local_db_encryption_wrong_key_fails_authentication(tmp_path):
    db_path = tmp_path / "db" / "codex-mem.sqlite3"
    codex_dir = tmp_path / ".codex"
    store = MemoryStore(
        db_path=db_path,
        codex_dir=codex_dir,
        default_project="tests",
        encryption_key="correct key",
    )
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Authenticated encryption",
            context="Wrong keys should not produce garbage plaintext.",
            resolution="AES-GCM authentication rejects invalid keys.",
            source="test",
        )
    )

    wrong_key_store = MemoryStore(
        db_path=db_path,
        codex_dir=codex_dir,
        default_project="tests",
        encryption_key="wrong key",
    )

    loaded = wrong_key_store.get(entry.id)
    assert loaded is not None
    assert loaded.title == "[DECRYPTION FAILED]"
    assert loaded.context == "[DECRYPTION FAILED]"
    assert loaded.resolution == "[DECRYPTION FAILED]"


def test_local_db_encryption_damaged_ciphertext_fails_safely(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        encryption_key="correct key",
    )
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Damaged ciphertext",
            context="Malformed encrypted values should not leak partial plaintext.",
            resolution="Return a clear decryption failure marker.",
            source="test",
        )
    )

    with sqlite3.connect(tmp_path / "db" / "codex-mem.sqlite3") as conn:
        conn.execute("UPDATE memories SET context = ? WHERE id = ?", ("enc:v2:not-valid", entry.id))

    loaded = store.get(entry.id)
    assert loaded is not None
    assert loaded.context == "[DECRYPTION FAILED]"


def test_local_db_encryption_enabled_without_key_fails_startup(tmp_path, monkeypatch):
    class FakeSettings:
        db_path = tmp_path / "db" / "codex-mem.sqlite3"
        codex_dir = tmp_path / ".codex"
        default_project = "tests"
        vector_backend = "local"
        chroma_url = "http://127.0.0.1:8000"
        pgvector_dsn = ""
        db_encryption_enabled = True
        db_encryption_key = ""

    memory.get_store.cache_clear()
    monkeypatch.setattr(memory, "get_settings", lambda: FakeSettings())

    with pytest.raises(RuntimeError, match="CODEX_MEM_DB_ENCRYPTION_KEY"):
        memory.get_store()

    memory.get_store.cache_clear()


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


def test_manual_update_and_delete_are_written_to_audit_log(tmp_path, monkeypatch):
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
            "title": "Audit me",
            "context": "This memory will be edited and deleted.",
            "source": "manual",
            "project": "tests",
        },
    )
    memory_id = created.json()["id"]

    assert client.patch(f"/memory/{memory_id}", json={"title": "Audited edit"}).status_code == 200
    assert client.delete(f"/memory/{memory_id}").status_code == 200

    audit = client.get("/memory/audit", params={"memory_id": memory_id})
    assert audit.status_code == 200
    events = audit.json()
    assert [event["action"] for event in events] == ["delete", "update"]
    assert events[0]["title"] == "Audited edit"
    exported = json.loads((tmp_path / ".codex" / "AUDIT.json").read_text(encoding="utf-8"))
    assert [event["memory_id"] for event in exported] == [memory_id, memory_id]


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

        def upsert(self, record: VectorRecord) -> None:
            return None

        def delete(self, memory_id: str) -> None:
            return None

        def search(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            return []

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
    chroma = create_vector_store(
        "chroma",
        chroma_url="http://chroma.local",
        chroma_collection="memories",
        chroma_timeout_seconds=9,
    )
    pgvector = create_vector_store("pgvector", pgvector_dsn="postgresql://memory")
    fallback = create_vector_store("chroma", allow_local_fallback=True)

    assert isinstance(chroma, ChromaVectorStore)
    assert chroma.url == "http://chroma.local"
    assert chroma.collection == "memories"
    assert chroma.timeout_seconds == 9
    assert chroma.embed("query")
    assert isinstance(pgvector, PgVectorStore)
    assert pgvector.dsn == "postgresql://memory"
    assert pgvector.embed("query")
    assert isinstance(fallback, LocalVectorStore)


def test_chroma_vector_store_uses_client_for_records():
    class FakeChromaClient:
        def __init__(self):
            self.upserted = None
            self.deleted = None
            self.queries = []

        def upsert(self, record: VectorRecord) -> None:
            self.upserted = record

        def delete(self, memory_id: str) -> None:
            self.deleted = memory_id

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            self.queries.append((query_vector, limit, project))
            return []

    client = FakeChromaClient()
    vector_store = ChromaVectorStore(url="http://chroma.local", client=client)
    record = VectorRecord(memory_id="mem_chroma", embedding=[1.0], document="doc", metadata={"project": "tests"})

    vector_store.upsert(record)
    assert vector_store.search([1.0], limit=3, project="tests") == []
    vector_store.delete(record.memory_id)

    assert client.upserted == record
    assert client.queries == [([1.0], 3, "tests")]
    assert client.deleted == "mem_chroma"


def test_memory_store_upserts_chroma_records_on_store_and_update(tmp_path):
    class FakeChromaClient:
        def __init__(self):
            self.records = []

        def upsert(self, record: VectorRecord) -> None:
            self.records.append(record)

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            return []

    client = FakeChromaClient()
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=ChromaVectorStore(url="http://chroma.local", client=client),
    )

    entry = store.store(MemoryCreate(type="fact", title="Chroma record", context="Stored in Chroma.", source="test"))
    store.update(entry.id, MemoryUpdate(context="Updated in Chroma."))

    assert [record.memory_id for record in client.records] == [entry.id, entry.id]
    assert all(record.embedding for record in client.records)
    assert client.records[0].metadata == {"project": "tests", "type": "fact"}
    assert "Updated in Chroma." in client.records[1].document


def test_memory_store_uses_chroma_similarity_search(tmp_path):
    class FakeChromaClient:
        def __init__(self):
            self.search_id = None
            self.queries = []

        def upsert(self, record: VectorRecord) -> None:
            self.search_id = record.memory_id

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            self.queries.append((query_vector, limit, project))
            return [VectorSearchResult(memory_id=self.search_id, score=0.92, metadata={"project": "tests"})]

    client = FakeChromaClient()
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=ChromaVectorStore(url="http://chroma.local", client=client),
    )
    entry = store.store(MemoryCreate(type="fact", title="Adapter indexed", context="No lexical overlap.", source="test"))

    results = store.search(query="remote nearest neighbor", track_usage=False)

    assert results[0].entry.id == entry.id
    assert "external vector backend similarity" in results[0].reason
    assert client.queries[0][2] == "tests"


def test_chroma_vector_store_surfaces_client_failure():
    class FailingChromaClient:
        def upsert(self, record: VectorRecord) -> None:
            raise VectorBackendUnavailable("Chroma unavailable")

        def delete(self, memory_id: str) -> None:
            raise VectorBackendUnavailable("Chroma unavailable")

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            raise VectorBackendUnavailable("Chroma unavailable")

    vector_store = ChromaVectorStore(url="http://chroma.local", client=FailingChromaClient())
    record = VectorRecord(memory_id="mem_chroma", embedding=[1.0], document="doc", metadata={})

    with pytest.raises(VectorBackendUnavailable, match="Chroma unavailable"):
        vector_store.upsert(record)


def test_pgvector_store_uses_sql_client_for_records():
    class FakePgVectorClient:
        def __init__(self):
            self.schema_ready = False
            self.upserted = None
            self.deleted = None
            self.queries = []

        def ensure_schema(self) -> None:
            self.schema_ready = True

        def upsert(self, record: VectorRecord) -> None:
            self.upserted = record

        def delete(self, memory_id: str) -> None:
            self.deleted = memory_id

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            self.queries.append((query_vector, limit, project))
            return [VectorSearchResult(memory_id="mem_pg", score=0.88, metadata={"project": "tests"})]

    client = FakePgVectorClient()
    vector_store = PgVectorStore(dsn="postgresql://memory", client=client)
    record = VectorRecord(memory_id="mem_pg", embedding=[0.1, 0.2], document="doc", metadata={"project": "tests"})

    vector_store.upsert(record)
    results = vector_store.search([0.1, 0.2], limit=2, project="tests")
    vector_store.delete(record.memory_id)

    assert client.upserted == record
    assert client.queries == [([0.1, 0.2], 2, "tests")]
    assert client.deleted == "mem_pg"
    assert results[0].memory_id == "mem_pg"


def test_memory_store_initializes_pgvector_schema(tmp_path):
    class FakePgVectorClient:
        def __init__(self):
            self.schema_ready = False

        def ensure_schema(self) -> None:
            self.schema_ready = True

        def upsert(self, record: VectorRecord) -> None:
            return None

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            return []

    client = FakePgVectorClient()
    MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=PgVectorStore(dsn="postgresql://memory", client=client),
    )

    assert client.schema_ready is True


def test_pgvector_schema_failure_is_diagnostic(tmp_path):
    class FailingPgVectorClient:
        def ensure_schema(self) -> None:
            raise VectorBackendUnavailable("pgvector extension is not installed")

        def upsert(self, record: VectorRecord) -> None:
            return None

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            return []

    with pytest.raises(VectorBackendUnavailable, match="pgvector extension"):
        MemoryStore(
            db_path=tmp_path / "db" / "codex-mem.sqlite3",
            codex_dir=tmp_path / ".codex",
            default_project="tests",
            vector_store=PgVectorStore(dsn="postgresql://memory", client=FailingPgVectorClient()),
        )


def test_pgvector_missing_dsn_has_clear_error():
    vector_store = PgVectorStore(dsn="")

    with pytest.raises(VectorBackendUnavailable, match="requires CODEX_MEM_PGVECTOR_DSN"):
        vector_store.ensure_schema()


def test_memory_store_upserts_pgvector_records_on_store_and_update(tmp_path):
    class FakePgVectorClient:
        def __init__(self):
            self.records = []

        def ensure_schema(self) -> None:
            return None

        def upsert(self, record: VectorRecord) -> None:
            self.records.append(record)

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            return []

    client = FakePgVectorClient()
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=PgVectorStore(dsn="postgresql://memory", client=client),
    )

    entry = store.store(MemoryCreate(type="fact", title="pgvector record", context="Stored in pgvector.", source="test"))
    store.update(entry.id, MemoryUpdate(context="Updated in pgvector."))

    assert [record.memory_id for record in client.records] == [entry.id, entry.id]
    assert all(record.embedding for record in client.records)
    assert client.records[0].metadata == {"project": "tests", "type": "fact"}
    assert "Updated in pgvector." in client.records[1].document


def test_memory_store_uses_pgvector_similarity_search(tmp_path):
    class FakePgVectorClient:
        def __init__(self):
            self.search_id = None
            self.queries = []

        def ensure_schema(self) -> None:
            return None

        def upsert(self, record: VectorRecord) -> None:
            self.search_id = record.memory_id

        def delete(self, memory_id: str) -> None:
            return None

        def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list:
            self.queries.append((query_vector, limit, project))
            return [VectorSearchResult(memory_id=self.search_id, score=0.9, metadata={"project": "tests"})]

    client = FakePgVectorClient()
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
        vector_store=PgVectorStore(dsn="postgresql://memory", client=client),
    )
    entry = store.store(MemoryCreate(type="fact", title="pgvector indexed", context="No lexical overlap.", source="test"))

    results = store.search(query="postgres nearest neighbor", track_usage=False)

    assert results[0].entry.id == entry.id
    assert "external vector backend similarity" in results[0].reason
    assert client.queries[0][2] == "tests"


def test_unsupported_vector_backend_has_clear_error():
    with pytest.raises(ValueError, match="Unsupported vector backend: mystery"):
        create_vector_store("mystery")


def test_local_vector_store_exposes_external_backend_contract():
    vector_store = LocalVectorStore()
    embedding = vector_store.embed("contract test")
    record = VectorRecord(
        memory_id="mem_contract",
        embedding=embedding,
        document="contract test",
        metadata={"project": "tests"},
    )

    vector_store.upsert(record)
    assert vector_store.search(embedding, limit=5, project="tests") == []
    vector_store.delete(record.memory_id)


def test_repeated_errors_detects_recurring_bug_titles(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    first = store.store(
        MemoryCreate(
            type="bug",
            title="npm.ps1 execution policy blocked validation",
            context="First session saw PowerShell block npm.ps1.",
            source="post-tool-use",
        )
    )
    second = store.store(
        MemoryCreate(
            type="bug",
            title="npm.ps1 execution policy blocked validation",
            context="Later session hit the same validation failure.",
            source="post-tool-use",
        )
    )
    store.store(
        MemoryCreate(
            type="bug",
            title="Unrelated transient API timeout",
            context="Only happened once.",
            source="post-tool-use",
        )
    )

    client = TestClient(app)
    response = client.get("/memory/smart/repeated-errors")

    assert response.status_code == 200
    repeated = response.json()["repeated_errors"]
    assert len(repeated) == 1
    assert repeated[0]["count"] == 2
    assert repeated[0]["memory_ids"] == [second.id, first.id]


def test_anti_patterns_detect_repeated_failures(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    first = store.store(
        MemoryCreate(type="bug", title="Retrying without API health check", context="Failed once.", source="test")
    )
    second = store.store(
        MemoryCreate(type="bug", title="Retrying without API health check", context="Failed again.", source="test")
    )

    client = TestClient(app)
    response = client.get("/memory/smart/anti-patterns")

    assert response.status_code == 200
    anti_patterns = response.json()["anti_patterns"]
    assert anti_patterns[0]["title"] == "Anti-pattern: Retrying without API health check"
    assert anti_patterns[0]["evidence_count"] == 2
    assert anti_patterns[0]["memory_ids"] == [second.id, first.id]


def test_reused_solutions_detects_frequently_used_entries(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    reused = store.store(
        MemoryCreate(
            type="solution",
            title="Use npm.cmd on PowerShell",
            context="PowerShell execution policy can block npm.ps1.",
            resolution="Run npm.cmd for validation commands.",
            source="test",
        )
    )
    store.store(
        MemoryCreate(
            type="solution",
            title="One-off setup solution",
            context="Only used once.",
            resolution="Keep as normal memory.",
            source="test",
        )
    )
    store.search(query="npm PowerShell validation", limit=1)
    store.inject_context(query="npm PowerShell", limit=1, token_budget=500)

    client = TestClient(app)
    response = client.get("/memory/smart/reused-solutions", params={"min_uses": 2})

    assert response.status_code == 200
    solutions = response.json()["reused_solutions"]
    assert len(solutions) == 1
    assert solutions[0]["id"] == reused.id
    assert solutions[0]["total_uses"] >= 2


def test_promote_best_practices_creates_pattern_from_reused_solution(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    solution = store.store(
        MemoryCreate(
            type="solution",
            title="Use npm.cmd on PowerShell",
            context="PowerShell execution policy can block npm.ps1.",
            resolution="Use npm.cmd for validation commands on Windows.",
            confidence=0.9,
            tags=["windows", "validation"],
            source="test",
        )
    )
    store.search(query="npm PowerShell validation", limit=1)
    store.search(query="npm.cmd validation", limit=1)

    client = TestClient(app)
    response = client.post("/memory/smart/promote-best-practices", params={"min_uses": 2})

    assert response.status_code == 200
    promoted = response.json()["promoted"]
    assert len(promoted) == 1
    assert promoted[0]["type"] == "pattern"
    assert promoted[0]["title"] == "Best practice: Use npm.cmd on PowerShell"
    assert "best-practice" in promoted[0]["tags"]
    assert promoted[0]["context"] == solution.context


def test_generate_summary_memory_creates_compact_fact(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    store.store(
        MemoryCreate(
            type="decision",
            title="Use SQLite first",
            context="SQLite keeps the MVP local.",
            resolution="Keep memory in SQLite before remote backends.",
            source="test",
        )
    )
    store.store(
        MemoryCreate(
            type="solution",
            title="Use history table",
            context="Memory updates need auditability.",
            resolution="Record immutable snapshots in memory_history.",
            source="test",
        )
    )

    client = TestClient(app)
    response = client.post("/memory/smart/summary", params={"query": "SQLite memory", "limit": 2})

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["type"] == "fact"
    assert summary["title"] == "Summary: SQLite memory"
    assert "summary" in summary["tags"]
    assert "Use SQLite first" in summary["context"]


def test_archive_low_value_memories_archives_old_unused_entries(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    old = store.store(
        MemoryCreate(
            type="fact",
            title="Low confidence stale note",
            context="This was never reused.",
            confidence=0.2,
            source="test",
        )
    )
    fresh = store.store(
        MemoryCreate(
            type="fact",
            title="Fresh low confidence note",
            context="Too new to archive.",
            confidence=0.2,
            source="test",
        )
    )
    with store._connect() as conn:
        conn.execute("UPDATE memories SET timestamp = ? WHERE id = ?", ("2026-01-01T00:00:00+00:00", old.id))

    client = TestClient(app)
    response = client.post("/memory/smart/archive-low-value", params={"unused_days": 1})

    assert response.status_code == 200
    archived = response.json()["archived"]
    assert [entry["id"] for entry in archived] == [old.id]
    assert archived[0]["status"] == "archived"
    assert store.get(old.id) is None
    assert store.get(fresh.id) is not None


def test_consolidation_job_runs_summary_and_archive(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    store.store(
        MemoryCreate(
            type="decision",
            title="Use SQLite first",
            context="SQLite keeps the MVP local.",
            confidence=0.8,
            source="test",
        )
    )
    stale = store.store(
        MemoryCreate(
            type="fact",
            title="Stale guess",
            context="Old low confidence note.",
            confidence=0.1,
            source="test",
        )
    )
    with store._connect() as conn:
        conn.execute("UPDATE memories SET timestamp = ? WHERE id = ?", ("2026-01-01T00:00:00+00:00", stale.id))

    client = TestClient(app)
    response = client.post("/memory/smart/consolidate", params={"query": "SQLite"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["title"] == "Summary: SQLite"
    assert [entry["id"] for entry in body["archived"]] == [stale.id]


def test_cross_entry_linking_connects_bug_solution_and_pattern(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    bug = store.store(
        MemoryCreate(type="bug", title="npm.ps1 blocked validation", context="Failure.", tags=["npm"], source="test")
    )
    solution = store.store(
        MemoryCreate(type="solution", title="Use npm.cmd on PowerShell", context="Fix.", tags=["npm"], source="test")
    )
    pattern = store.store(
        MemoryCreate(
            type="pattern",
            title="Best practice: Use npm.cmd on PowerShell",
            context="Practice.",
            tags=["best-practice"],
            source="test",
        )
    )

    client = TestClient(app)
    response = client.post("/memory/smart/link-related")

    assert response.status_code == 200
    links = {(link["from_id"], link["to_id"], link["relation"]) for link in response.json()["links"]}
    assert (bug.id, solution.id, "bug_solution") in links
    assert (solution.id, pattern.id, "solution_pattern") in links


def test_recalculate_confidence_uses_usage_and_validation(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    entry = store.store(
        MemoryCreate(
            type="solution",
            title="Validated reusable fix",
            context="Reusable fix.",
            confidence=0.5,
            tags=["validated"],
            source="test",
        )
    )
    store.search(query="Validated reusable", limit=1)

    client = TestClient(app)
    response = client.post("/memory/smart/recalculate-confidence")

    assert response.status_code == 200
    updated = response.json()["updated"]
    assert updated[0]["id"] == entry.id
    assert updated[0]["confidence"] > 0.5
    history = store.history(memory_id=entry.id)
    assert history[0].action == "update"


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
    assert any("summarized due to token budget" in entry.reason for entry in trace.entries)
    assert len(additional_context) <= 450


def test_injection_preview_reports_budget_without_usage_side_effects(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Preview memory injection decisions",
            context="Preview should explain what context would be injected.",
            resolution="Do not increment usage counters during preview.",
            source="test",
        )
    )

    client = TestClient(app)
    response = client.get(
        "/memory/inject-preview",
        params={"query": "preview injection", "limit": 1, "token_budget": 500},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"] == "preview injection"
    assert body["token_budget"] == 500
    assert body["selected_context"][0]["id"] == entry.id
    assert body["selected_context"][0]["tokens"] > 0
    assert body["selected_estimated_tokens"] <= body["total_estimated_tokens"]
    assert "Preview memory injection decisions" in body["additional_context"]
    unchanged = store.get(entry.id)
    assert unchanged is not None
    assert unchanged.retrieved_count == 0
    assert unchanged.injected_count == 0
    assert store.latest_injection_trace() is None


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


def test_markdown_import_back_into_sqlite(tmp_path):
    codex_dir = tmp_path / ".codex"
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=codex_dir,
        default_project="tests",
    )
    markdown = codex_dir / "import.md"
    markdown.write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## Imported decision",
                "",
                "- type: `decision`",
                "- confidence: `0.90`",
                "- importance: `0.80`",
                "- pinned: `False`",
                "- file_paths: `apps/api/app/storage/sqlite.py`",
                "- source: `markdown`",
                "- project: `tests`",
                "- tags: `import, markdown`",
                "",
                "### Context",
                "",
                "Markdown should import into SQLite.",
                "",
                "### Resolution",
                "",
                "Parse exported metadata and text sections.",
            ]
        ),
        encoding="utf-8",
    )

    imported = store.import_markdown(markdown)

    assert len(imported) == 1
    assert imported[0].type.value == "decision"
    assert imported[0].title == "Imported decision"
    assert imported[0].file_paths == ["apps/api/app/storage/sqlite.py"]
    assert imported[0].tags == ["import", "markdown"]


def test_markdown_migration_assistant_endpoint_imports_file(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    markdown = tmp_path / "legacy-memory.md"
    markdown.write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## Legacy fix",
                "",
                "- type: `solution`",
                "- source: `legacy-md`",
                "- project: `tests`",
                "",
                "### Context",
                "",
                "Markdown-only memory existed before SQLite.",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": str(markdown)})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(markdown)
    assert body["imported"][0]["title"] == "Legacy fix"
    assert body["imported"][0]["source"] == "legacy-md"


def test_markdown_import_endpoint_imports_default_codex_memory(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    (tmp_path / ".codex" / "MEMORY.md").write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## Default import",
                "",
                "- type: `fact`",
                "- source: `test`",
                "",
                "### Context",
                "",
                "Default .codex import works.",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={})

    assert response.status_code == 200
    assert response.json()["imported"][0]["title"] == "Default import"


def test_markdown_import_endpoint_rejects_path_traversal(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "repo" / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / "repo" / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    secret = tmp_path / "secret.md"
    secret.write_text("# secret\n", encoding="utf-8")

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": "../secret.md"})

    assert response.status_code == 403
    assert "outside the allowed repository boundary" in response.json()["detail"]


def test_markdown_import_endpoint_rejects_absolute_path_outside_repo(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "repo" / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / "repo" / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": str(outside)})

    assert response.status_code == 403
    assert "allow_external_paths" in response.json()["detail"]


def test_markdown_import_endpoint_rejects_symlink_outside_repo(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "repo" / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / "repo" / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    link = tmp_path / "repo" / "linked.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not supported in this environment")

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": "linked.md"})

    assert response.status_code == 403


def test_markdown_import_endpoint_allows_external_path_with_opt_in(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "repo" / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / "repo" / ".codex",
        default_project="tests",
    )

    class FakeSettings:
        migration_allow_external_paths = True

    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(memory, "get_settings", lambda: FakeSettings())
    outside = tmp_path / "outside.md"
    outside.write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## External import",
                "",
                "- type: `fact`",
                "- source: `external-md`",
                "",
                "### Context",
                "",
                "External migration is explicitly allowed.",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": str(outside)})

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == str(outside.resolve())
    assert body["imported"][0]["title"] == "External import"


def test_markdown_import_endpoint_rejects_directories_large_files_and_non_markdown(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    large = tmp_path / "large.md"
    large.write_text("x" * (memory.MARKDOWN_IMPORT_MAX_BYTES + 1), encoding="utf-8")
    text = tmp_path / "notes.txt"
    text.write_text("not markdown", encoding="utf-8")

    client = TestClient(app)

    directory_response = client.post("/memory/import/markdown", json={"path": "."})
    large_response = client.post("/memory/import/markdown", json={"path": "large.md"})
    text_response = client.post("/memory/import/markdown", json={"path": "notes.txt"})

    assert directory_response.status_code == 400
    assert "must be a file" in directory_response.json()["detail"]
    assert large_response.status_code == 400
    assert "byte limit" in large_response.json()["detail"]
    assert text_response.status_code == 400
    assert "only accepts .md" in text_response.json()["detail"]


def test_markdown_import_endpoint_rejects_invalid_markdown_without_crashing(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    invalid = tmp_path / "invalid.md"
    invalid.write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## Invalid metadata",
                "",
                "- type: `solution`",
                "- confidence: `not-a-number`",
                "",
                "### Context",
                "",
                "This entry should produce a clear 400 response.",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post("/memory/import/markdown", json={"path": "invalid.md"})

    assert response.status_code == 400
    assert "Invalid Markdown import" in response.json()["detail"]
    assert "non-numeric confidence or importance" in response.json()["detail"]


def test_markdown_export_import_round_trip(tmp_path):
    source = MemoryStore(
        db_path=tmp_path / "source" / "db.sqlite3",
        codex_dir=tmp_path / "source" / ".codex",
        default_project="tests",
    )
    original = source.store(
        MemoryCreate(
            type="solution",
            title="Round trip memory",
            context="Exported context survives.",
            resolution="Imported resolution survives.",
            confidence=0.8,
            tags=["round-trip"],
            source="test",
        )
    )
    exported = tmp_path / "source" / ".codex" / "MEMORY.md"

    target = MemoryStore(
        db_path=tmp_path / "target" / "db.sqlite3",
        codex_dir=tmp_path / "target" / ".codex",
        default_project="tests",
    )
    imported = target.import_markdown(exported)

    assert len(imported) == 1
    assert imported[0].title == original.title
    assert imported[0].context == original.context
    assert imported[0].resolution == original.resolution
    assert imported[0].tags == ["round-trip"]


def test_repo_sync_exports_selected_entries(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(memory, "get_settings", lambda: type("Settings", (), {"sync_enabled": True})())

    selected = store.store(
        MemoryCreate(type="decision", title="Sync this", context="Selected.", tags=["repo-sync"], source="test")
    )
    store.store(MemoryCreate(type="fact", title="Do not sync", context="Unselected.", source="test"))

    client = TestClient(app)
    response = client.post("/memory/sync/repo")

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["synced"]] == [selected.id]
    assert store.audit_log(memory_id=selected.id)[0].action == "sync"
    exported = json.loads((tmp_path / ".codex" / "SYNCED_MEMORY.json").read_text(encoding="utf-8"))
    assert exported[0]["title"] == "Sync this"


def test_repo_sync_requires_explicit_opt_in(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(memory, "get_settings", lambda: type("Settings", (), {"sync_enabled": False})())

    client = TestClient(app)
    response = client.post("/memory/sync/repo")

    assert response.status_code == 403
    assert "opt in" in response.json()["detail"]


def test_project_search_includes_global_scope(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    global_entry = store.store(
        MemoryCreate(type="fact", title="Global memory rule", context="Applies everywhere.", project="global", source="test")
    )
    local_entry = store.store(
        MemoryCreate(type="fact", title="Local memory rule", context="Applies here.", project="tests", source="test")
    )

    results = store.search(query="memory rule", project="tests", track_usage=False)

    assert {result.entry.id for result in results} == {global_entry.id, local_entry.id}


def test_default_search_isolates_local_global_and_team_scopes(tmp_path):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    global_entry = store.store(
        MemoryCreate(type="fact", title="Shared scope memory", context="Global.", project="global", source="test")
    )
    local_entry = store.store(
        MemoryCreate(type="fact", title="Shared scope memory", context="Local.", project="tests", source="test")
    )
    team_entry = store.store(
        MemoryCreate(type="fact", title="Shared scope memory", context="Team.", project="team", source="test")
    )

    default_results = store.search(query="shared scope", track_usage=False)
    team_results = store.search(query="shared scope", project="team", track_usage=False)

    assert {result.entry.id for result in default_results} == {global_entry.id, local_entry.id}
    assert {result.entry.id for result in team_results} == {global_entry.id, team_entry.id}


def test_cross_project_learning_promotes_memory_to_global_scope(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    local = store.store(
        MemoryCreate(type="solution", title="Reusable setup fix", context="Works across repos.", source="test")
    )

    client = TestClient(app)
    response = client.post(f"/memory/{local.id}/promote-global")

    assert response.status_code == 200
    promoted = response.json()
    assert promoted["project"] == "global"
    assert promoted["source"] == "cross-project"
    assert "cross-project" in promoted["tags"]
    team_results = store.search(query="reusable setup", project="team", track_usage=False)
    assert promoted["id"] in {result.entry.id for result in team_results}


def test_team_memory_backend_searches_team_scope(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type("Settings", (), {"team_backend": "local", "team_id": "default", "team_role": "reader"})(),
    )
    team_entry = store.store(
        MemoryCreate(
            type="pattern",
            title="Team workflow",
            context="Shared team note.",
            project="team:default",
            source="test",
        )
    )
    store.store(MemoryCreate(type="pattern", title="Local workflow", context="Local note.", source="test"))

    client = TestClient(app)
    response = client.get("/memory/team/search", params={"query": "workflow"})

    assert response.status_code == 200
    assert [result["entry"]["id"] for result in response.json()["results"]] == [team_entry.id]


def test_team_memory_search_isolated_by_team_id(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type("Settings", (), {"team_backend": "local", "team_id": "a", "team_role": "reader"})(),
    )
    team_a = store.store(
        MemoryCreate(type="pattern", title="Team workflow", context="Team A note.", project="team:a", source="test")
    )
    store.store(
        MemoryCreate(type="pattern", title="Team workflow", context="Team B note.", project="team:b", source="test")
    )
    store.store(
        MemoryCreate(type="pattern", title="Team workflow", context="Global note.", project="global", source="test")
    )

    client = TestClient(app)
    response = client.get("/memory/team/search", params={"query": "workflow"})

    assert response.status_code == 200
    assert [result["entry"]["id"] for result in response.json()["results"]] == [team_a.id]


def test_team_memory_search_rejects_invalid_role(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type("Settings", (), {"team_backend": "local", "team_id": "default", "team_role": "none"})(),
    )

    client = TestClient(app)
    response = client.get("/memory/team/search", params={"query": "workflow"})

    assert response.status_code == 403
    assert "not allowed" in response.json()["detail"]


def test_team_memory_write_requires_opt_in_and_writer_role(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )

    def fake_settings(write_enabled: bool, role: str):
        return type(
            "Settings",
            (),
            {
                "team_backend": "local",
                "team_id": "default",
                "team_role": role,
                "team_write_enabled": write_enabled,
            },
        )()

    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(memory, "get_settings", lambda: fake_settings(False, "writer"))
    client = TestClient(app)
    payload = {"type": "fact", "title": "Team write", "context": "Opt-in required.", "project": "team:default"}

    denied = client.post("/memory", json=payload)
    monkeypatch.setattr(memory, "get_settings", lambda: fake_settings(True, "reader"))
    role_denied = client.post("/memory", json=payload)
    monkeypatch.setattr(memory, "get_settings", lambda: fake_settings(True, "writer"))
    accepted = client.post("/memory", json=payload)

    assert denied.status_code == 403
    assert "writes are disabled" in denied.json()["detail"]
    assert role_denied.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["project"] == "team:default"


def test_team_memory_create_is_written_to_audit_log(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {"team_backend": "local", "team_id": "default", "team_role": "writer", "team_write_enabled": True},
        )(),
    )
    client = TestClient(app)

    created = client.post(
        "/memory",
        json={"type": "fact", "title": "Team audit", "context": "Audit this.", "project": "team:default"},
    )
    audit = client.get("/memory/audit", params={"memory_id": created.json()["id"]})

    assert created.status_code == 200
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "create"


def test_general_search_validates_team_scope_access(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    team_entry = store.store(
        MemoryCreate(type="fact", title="Team search", context="Team-only.", project="team:default", source="test")
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {"team_backend": "local", "team_id": "default", "team_role": "reader", "team_write_enabled": False},
        )(),
    )
    client = TestClient(app)

    local = client.get("/memory/search", params={"query": "team search"})
    team = client.get("/memory/search", params={"query": "team search", "project": "team:default"})
    other_team = client.get("/memory/search", params={"query": "team search", "project": "team:other"})

    assert local.status_code == 200
    assert team_entry.id not in {result["entry"]["id"] for result in local.json()["results"]}
    assert team.status_code == 200
    assert [result["entry"]["id"] for result in team.json()["results"]] == [team_entry.id]
    assert other_team.status_code == 403


def test_shared_memory_namespace_search_isolated_by_namespace(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    alpha = store.store(
        MemoryCreate(type="fact", title="Namespace rule", context="Alpha shared.", project="shared:alpha", source="test")
    )
    store.store(
        MemoryCreate(type="fact", title="Namespace rule", context="Beta shared.", project="shared:beta", source="test")
    )
    store.store(MemoryCreate(type="fact", title="Namespace rule", context="Global.", project="global", source="test"))

    client = TestClient(app)
    response = client.get("/memory/shared/Alpha/search", params={"query": "namespace"})

    assert response.status_code == 200
    assert [result["entry"]["id"] for result in response.json()["results"]] == [alpha.id]


def test_shared_memory_write_requires_opt_in(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )

    def fake_settings(write_enabled: bool):
        return type("Settings", (), {"shared_write_enabled": write_enabled})()

    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(memory, "get_settings", lambda: fake_settings(False))
    client = TestClient(app)
    payload = {"type": "fact", "title": "Shared write", "context": "Opt-in required.", "project": "shared:alpha"}

    denied = client.post("/memory", json=payload)
    monkeypatch.setattr(memory, "get_settings", lambda: fake_settings(True))
    accepted = client.post("/memory", json=payload)

    assert denied.status_code == 403
    assert "Shared memory writes are disabled" in denied.json()["detail"]
    assert accepted.status_code == 200
    assert accepted.json()["project"] == "shared:alpha"
    assert store.audit_log(memory_id=accepted.json()["id"])[0].action == "create"


def test_shared_namespace_name_is_normalized():
    assert memory.shared_namespace_project("Alpha Docs/Runtime") == "shared:alpha-docs-runtime"


def test_shared_namespace_rejects_empty_or_invalid_name():
    with pytest.raises(Exception, match="Shared namespace must contain"):
        memory.shared_namespace_project("!!!")


def test_shared_memory_namespaces_are_listed(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    store.store(MemoryCreate(type="fact", title="Alpha", context="Shared.", project="shared:alpha", source="test"))
    store.store(MemoryCreate(type="fact", title="Beta", context="Shared.", project="shared:beta", source="test"))
    store.store(MemoryCreate(type="fact", title="Local", context="Local.", project="tests", source="test"))

    client = TestClient(app)
    response = client.get("/memory/shared/namespaces")

    assert response.status_code == 200
    assert response.json() == {"namespaces": ["alpha", "beta"]}


def test_shared_namespace_search_supports_tag_filters(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    keep = store.store(
        MemoryCreate(
            type="fact",
            title="Namespace kept",
            context="Shared with tag.",
            project="shared:alpha",
            tags=["keep"],
            source="test",
        )
    )
    store.store(
        MemoryCreate(
            type="fact",
            title="Namespace dropped",
            context="Shared with other tag.",
            project="shared:alpha",
            tags=["drop"],
            source="test",
        )
    )

    client = TestClient(app)
    response = client.get("/memory/shared/alpha/search", params={"tags": "keep"})

    assert response.status_code == 200
    assert [result["entry"]["id"] for result in response.json()["results"]] == [keep.id]


def test_shared_namespace_index_supports_progressive_disclosure(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(
        MemoryCreate(type="fact", title="Namespace index", context="Compact shared index.", project="shared:alpha")
    )

    client = TestClient(app)
    response = client.get("/memory/shared/alpha/index", params={"query": "index", "profile": "short"})

    assert response.status_code == 200
    assert response.json()["results"][0]["id"] == entry.id


def test_memory_metadata_exposes_schema_version(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    client = TestClient(app)
    response = client.get("/memory/metadata")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "2"


def test_existing_database_schema_metadata_migrates_without_data_loss(tmp_path):
    db_path = tmp_path / "db" / "codex-mem.sqlite3"
    codex_dir = tmp_path / ".codex"
    store = MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")
    entry = store.store(MemoryCreate(type="fact", title="Keep during migration", context="Existing data survives."))
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE memory_metadata SET value = '1' WHERE key = 'schema_version'")

    migrated = MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")

    assert migrated.metadata()["schema_version"] == "2"
    loaded = migrated.get(entry.id)
    assert loaded is not None
    assert loaded.title == "Keep during migration"


def test_existing_database_migration_writes_backup_before_schema_update(tmp_path):
    db_path = tmp_path / "db" / "codex-mem.sqlite3"
    codex_dir = tmp_path / ".codex"
    store = MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")
    entry = store.store(MemoryCreate(type="fact", title="Backup before migration", context="Existing data survives."))
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE memory_metadata SET value = '1' WHERE key = 'schema_version'")

    MemoryStore(db_path=db_path, codex_dir=codex_dir, default_project="tests")

    backup_path = db_path.with_suffix(".sqlite3.v1-to-v2.bak")
    assert backup_path.exists()
    with sqlite3.connect(backup_path) as conn:
        conn.row_factory = sqlite3.Row
        backup_version = conn.execute("SELECT value FROM memory_metadata WHERE key = 'schema_version'").fetchone()
        backup_entry = conn.execute("SELECT title FROM memories WHERE id = ?", (entry.id,)).fetchone()
    assert backup_version["value"] == "1"
    assert backup_entry["title"] == "Backup before migration"


def test_config_diagnostics_endpoint(monkeypatch):
    class FakeSettings:
        def diagnostics(self):
            return {
                "config_path": ".codex/mem.config.json",
                "diagnostics": ["Config key 'inject_limit' must be at least 1; using 5."],
                "debug_verbose": False,
                "inject_limit": 5,
                "token_budget": 1200,
                "vector_backend": "local",
            }

    monkeypatch.setattr(memory, "get_settings", lambda: FakeSettings())

    client = TestClient(app)
    response = client.get("/memory/config/diagnostics")

    assert response.status_code == 200
    assert response.json()["diagnostics"] == ["Config key 'inject_limit' must be at least 1; using 5."]


def test_memory_stats_endpoint_reports_usage_metrics(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    store.store(
        MemoryCreate(
            type="bug",
            title="Auth regression",
            context="Authentication failed after refactor.",
            resolution="Reuse the validated auth fixture.",
            file_paths=["src/auth.ts"],
            source="test",
        )
    )
    store.inject_context(query="auth regression", limit=1, token_budget=500)

    client = TestClient(app)
    response = client.get("/memory/stats", params={"project": "tests", "impact": "true"})

    assert response.status_code == 200
    body = response.json()
    assert body["calls_by_command"]["inject"] == 1
    assert body["total_injected_memories"] == 1
    assert body["average_injected_tokens"] > 0
    assert body["max_injected_tokens"] >= body["average_injected_tokens"]
    assert body["skipped_due_to_budget"] == 0
    assert body["most_recalled_files"] == [{"file_path": "src/auth.ts", "count": 2}]
    assert body["most_used_memory_types"] == [{"type": "bug", "count": 2}]
    assert body["impact"]["memory_assisted_sessions"] == 1


def test_explain_memory_is_deterministic_and_redacts_secrets(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(
        MemoryCreate(
            type="decision",
            title="Do not expose token=secret-value",
            context="Use src/auth.ts for auth.",
            file_paths=["src/auth.ts"],
            tags=["auth"],
            source="test",
        )
    )

    client = TestClient(app)
    first = client.get(f"/memory/explain/{entry.id}")
    second = client.get(f"/memory/explain/{entry.id}")

    assert first.status_code == 200
    assert first.json() == second.json()
    body_text = json.dumps(first.json())
    assert "secret-value" not in body_text
    assert "src/auth.ts" in first.json()["file_path_evidence"]


def test_local_memory_viewer_is_served():
    client = TestClient(app)
    response = client.get("/memory/viewer")
    css = client.get("/memory/viewer/assets/viewer.css")
    js = client.get("/memory/viewer/assets/viewer.js")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Codex-Mem Viewer" in response.text
    assert "/memory/viewer/assets/viewer.css" in response.text
    assert "/memory/viewer/assets/viewer.js" in response.text
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert js.status_code == 200
    assert "application/javascript" in js.headers["content-type"]
    assert "/memory/search" in js.text
    assert "/memory/history" in js.text


def test_local_memory_viewer_endpoint_dependencies(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(MemoryCreate(type="fact", title="Viewer dependency", context="Viewer endpoint test."))

    client = TestClient(app)
    search = client.get("/memory/search", params={"query": "viewer"})
    debug = client.get("/memory/debug/search", params={"query": "viewer"})
    history = client.get("/memory/history", params={"memory_id": entry.id})
    audit = client.get("/memory/audit", params={"memory_id": entry.id})
    health = client.get("/memory/health/diagnostics")

    assert search.status_code == 200
    assert debug.status_code == 200
    assert history.status_code == 200
    assert audit.status_code == 200
    assert health.status_code == 200


def test_health_diagnostics_reports_core_components(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    client = TestClient(app)
    response = client.get("/memory/health/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "warning"
    components = {component["name"]: component["status"] for component in body["components"]}
    assert components["api"] == "ok"
    assert components["db"] == "ok"
    assert components["schema"] == "ok"
    assert components["vector"] == "ok"
    assert components["team"] == "ok"
    assert components["encryption"] == "warning"
    assert components["mcp"] == "ok"
    assert components["hooks"] == "ok"
    assert components["plugin"] == "ok"


def test_search_ranking_debug_view_returns_score_components(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="tests",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    entry = store.store(
        MemoryCreate(
            type="solution",
            title="Debug ranking view",
            context="Search debugging should explain ranking components.",
            confidence=0.9,
            importance=0.8,
            tags=["ranking"],
            source="test",
        )
    )

    client = TestClient(app)
    response = client.get("/memory/debug/search", params={"query": "ranking debug", "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "ranking debug"
    result = body["results"][0]
    assert result["entry"]["id"] == entry.id
    assert result["score"] > 0
    assert result["components"]["keyword"] > 0
    assert "semantic" in result["components"]
    assert "matched query terms" in result["reason"]
