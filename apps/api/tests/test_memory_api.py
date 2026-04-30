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

    selected = store.store(
        MemoryCreate(type="decision", title="Sync this", context="Selected.", tags=["repo-sync"], source="test")
    )
    store.store(MemoryCreate(type="fact", title="Do not sync", context="Unselected.", source="test"))

    client = TestClient(app)
    response = client.post("/memory/sync/repo")

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["synced"]] == [selected.id]
    exported = json.loads((tmp_path / ".codex" / "SYNCED_MEMORY.json").read_text(encoding="utf-8"))
    assert exported[0]["title"] == "Sync this"


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
    assert response.json()["schema_version"] == "1"
