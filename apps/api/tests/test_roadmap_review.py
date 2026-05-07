from pathlib import Path

from fastapi.testclient import TestClient

from app.core.models import MemoryCreate
from app.main import app
from app.routes import memory
from app.storage.sqlite import MemoryStore


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_roadmap_review_all_items_are_completed():
    roadmap = (REPO_ROOT / ".codex" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "- [ ]" not in roadmap
    assert "- [x] Full Brain:" in roadmap


def test_roadmap_review_core_memory_flow(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="review",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)

    client = TestClient(app)
    created = client.post(
        "/memory",
        json={
            "type": "decision",
            "title": "Review validates injection trace",
            "context": "A stored decision should be searchable and injectable.",
            "resolution": "Use debug endpoints to explain why it was selected.",
            "confidence": 0.9,
            "importance": 0.8,
            "tags": ["review"],
            "source": "roadmap-review",
            "project": "review",
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["id"]

    search_debug = client.get("/memory/debug/search", params={"query": "injection trace", "limit": 1})
    assert search_debug.status_code == 200
    assert search_debug.json()["results"][0]["entry"]["id"] == memory_id
    assert search_debug.json()["results"][0]["components"]["keyword"] > 0

    inject = client.get("/memory/inject", params={"query": "injection trace", "limit": 1})
    assert inject.status_code == 200
    body = inject.json()
    assert body["trace"]["entries"][0]["memory_id"] == memory_id
    assert "Review validates injection trace" in body["additional_context"]

    updated = client.patch(f"/memory/{memory_id}", json={"title": "Review validates audit trace"})
    assert updated.status_code == 200
    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200

    audit = client.get("/memory/audit", params={"memory_id": memory_id})
    assert audit.status_code == 200
    assert [event["action"] for event in audit.json()] == ["delete", "update"]


def test_roadmap_review_scopes_and_markdown_migration(tmp_path, monkeypatch):
    store = MemoryStore(
        db_path=tmp_path / "db" / "codex-mem.sqlite3",
        codex_dir=tmp_path / ".codex",
        default_project="review",
    )
    monkeypatch.setattr(memory, "get_store", lambda: store)
    monkeypatch.setattr(
        memory,
        "get_settings",
        lambda: type("Settings", (), {"team_backend": "local", "team_id": "default", "team_role": "reader"})(),
    )

    team_entry = store.store(
        MemoryCreate(type="fact", title="Review team note", context="Visible only in team scope.", project="team:default")
    )
    shared_entry = store.store(
        MemoryCreate(
            type="fact",
            title="Review shared note",
            context="Visible only in the named shared namespace.",
            project="shared:review",
        )
    )

    client = TestClient(app)
    team = client.get("/memory/team/search", params={"query": "review"})
    shared = client.get("/memory/shared/review/search", params={"query": "review"})

    assert [result["entry"]["id"] for result in team.json()["results"]] == [team_entry.id]
    assert [result["entry"]["id"] for result in shared.json()["results"]] == [shared_entry.id]

    markdown = tmp_path / "legacy.md"
    markdown.write_text(
        "\n".join(
            [
                "# MEMORY",
                "",
                "## Review imported memory",
                "",
                "- type: `solution`",
                "- source: `review-md`",
                "",
                "### Context",
                "",
                "Markdown migration should create a SQLite memory entry.",
            ]
        ),
        encoding="utf-8",
    )
    imported = client.post("/memory/import/markdown", json={"path": str(markdown)})

    assert imported.status_code == 200
    assert imported.json()["imported"][0]["title"] == "Review imported memory"
