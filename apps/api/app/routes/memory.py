from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.core.models import (
    AntiPatternResponse,
    ArchiveResponse,
    CompactIndexResponse,
    ConfidenceRecalculationResponse,
    ConsolidationResponse,
    CompactMemoryResult,
    InjectResponse,
    InjectionTrace,
    MarkdownImportRequest,
    MarkdownImportResponse,
    MemoryCreate,
    MemoryAuditEntry,
    MemoryEntry,
    MemoryHistoryEntry,
    MemoryLinkResponse,
    MemoryUpdate,
    PromotedBestPracticeResponse,
    RepeatedErrorResponse,
    RepoSyncResponse,
    ReusedSolutionResponse,
    SearchDebugResponse,
    SearchResponse,
    SummaryMemoryResponse,
)
from app.core.settings import get_settings
from app.storage.sqlite import MemoryStore
from app.storage.vector import create_vector_store

router = APIRouter(prefix="/memory", tags=["memory"])
MARKDOWN_IMPORT_MAX_BYTES = 1_000_000

RetrievalProfile = Literal["short", "normal", "deep"]
SEARCH_PROFILE_LIMITS = {
    "short": 3,
    "normal": 10,
    "deep": 25,
}
INJECT_PROFILE_LIMITS = {
    "short": 3,
    "normal": None,
    "deep": 15,
}


@lru_cache
def get_store() -> MemoryStore:
    settings = get_settings()
    if settings.db_encryption_enabled and not settings.db_encryption_key:
        raise RuntimeError("DB encryption is enabled but CODEX_MEM_DB_ENCRYPTION_KEY is empty.")
    return MemoryStore(
        db_path=settings.db_path,
        codex_dir=settings.codex_dir,
        default_project=settings.default_project,
        vector_store=create_vector_store(
            settings.vector_backend,
            chroma_url=settings.chroma_url,
            pgvector_dsn=settings.pgvector_dsn,
        ),
        encryption_key=settings.db_encryption_key if settings.db_encryption_enabled else None,
    )


@router.post("", response_model=MemoryEntry)
def store_memory(payload: MemoryCreate) -> MemoryEntry:
    return get_store().store(payload)


@router.patch("/{memory_id}", response_model=MemoryEntry)
def update_memory(memory_id: str, payload: MemoryUpdate) -> MemoryEntry:
    try:
        updated = get_store().update(memory_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not updated:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return updated


@router.get("/search", response_model=SearchResponse)
def query_memory(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "normal",
    type: str | None = None,
    project: str | None = None,
    path: str | None = None,
    after: str | None = None,
    before: str | None = None,
    tags: list[str] = Query(default=[]),
) -> SearchResponse:
    try:
        resolved_limit = limit or SEARCH_PROFILE_LIMITS[profile]
        results = get_store().search(
            query=query,
            limit=resolved_limit,
            memory_type=type,
            project=project,
            tags=tags,
            path=path,
            created_after=after,
            created_before=before,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid date/time filter: {error}") from error
    return SearchResponse(results=results)


@router.get("/index", response_model=CompactIndexResponse)
def compact_memory_index(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "short",
    type: str | None = None,
    project: str | None = None,
    path: str | None = None,
    after: str | None = None,
    before: str | None = None,
    tags: list[str] = Query(default=[]),
) -> CompactIndexResponse:
    try:
        results = get_store().search(
            query=query,
            limit=limit or SEARCH_PROFILE_LIMITS[profile],
            memory_type=type,
            project=project,
            tags=tags,
            path=path,
            created_after=after,
            created_before=before,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid date/time filter: {error}") from error
    return CompactIndexResponse(
        results=[
            CompactMemoryResult(
                id=result.entry.id,
                type=result.entry.type,
                title=result.entry.title,
                score=result.score,
                reason=result.reason,
                tags=result.entry.tags,
                file_paths=result.entry.file_paths,
            )
            for result in results
        ]
    )


@router.get("/inject", response_model=InjectResponse)
def inject_memory(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=20),
    profile: RetrievalProfile = "normal",
    token_budget: int | None = Query(default=None, ge=100, le=8000),
) -> InjectResponse:
    settings = get_settings()
    profile_limit = INJECT_PROFILE_LIMITS[profile] or settings.inject_limit
    additional_context, results, trace = get_store().inject_context(
        query=query,
        limit=limit or profile_limit,
        token_budget=token_budget or settings.token_budget,
    )
    return InjectResponse(additional_context=additional_context, results=results, trace=trace)


@router.get("/debug/injection", response_model=InjectionTrace | None)
def latest_injection_trace() -> InjectionTrace | None:
    return get_store().latest_injection_trace()


@router.get("/debug/search", response_model=SearchDebugResponse)
def search_ranking_debug(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "normal",
    type: str | None = None,
    project: str | None = None,
    path: str | None = None,
    after: str | None = None,
    before: str | None = None,
    tags: list[str] = Query(default=[]),
) -> SearchDebugResponse:
    try:
        results = get_store().search_debug(
            query=query,
            limit=limit or SEARCH_PROFILE_LIMITS[profile],
            memory_type=type,
            project=project,
            tags=tags,
            path=path,
            created_after=after,
            created_before=before,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid date/time filter: {error}") from error
    return SearchDebugResponse(query=query, results=results)


@router.get("/metadata")
def memory_metadata() -> dict[str, str]:
    return get_store().metadata()


@router.get("/config/diagnostics")
def config_diagnostics() -> dict:
    return get_settings().diagnostics()


@router.get("/viewer", response_class=HTMLResponse)
def local_memory_viewer() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex-Mem Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --ink: #111827;
      --muted: #667085;
      --line: #d7dde5;
      --accent: #0f766e;
      --panel: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 18px 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.94);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 { margin: 0; font-size: 18px; font-weight: 700; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      min-height: calc(100svh - 62px);
    }
    section { padding: 24px 28px; }
    aside {
      border-left: 1px solid var(--line);
      background: var(--panel);
      padding: 24px;
      overflow: auto;
    }
    form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 92px;
      gap: 10px;
      max-width: 760px;
    }
    input, button {
      height: 38px;
      border-radius: 6px;
      border: 1px solid var(--line);
      font: inherit;
    }
    input { padding: 0 12px; background: #fff; color: var(--ink); }
    button { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 650; cursor: pointer; }
    .meta { color: var(--muted); margin: 14px 0 18px; }
    .list { display: grid; gap: 1px; border-top: 1px solid var(--line); max-width: 980px; }
    .row {
      background: var(--panel);
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr) 80px;
      gap: 16px;
      align-items: start;
    }
    .type { color: var(--accent); font-weight: 700; }
    .title { font-weight: 700; margin-bottom: 4px; }
    .text { color: var(--muted); overflow-wrap: anywhere; }
    .score { color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
    h2 { margin: 0 0 14px; font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.08em; }
    .event { padding: 11px 0; border-bottom: 1px solid var(--line); }
    .event strong { display: block; }
    @media (max-width: 820px) {
      main { grid-template-columns: 1fr; }
      aside { border-left: 0; border-top: 1px solid var(--line); }
      header, section, aside { padding-left: 16px; padding-right: 16px; }
      .row { grid-template-columns: 1fr; gap: 4px; }
      .score { text-align: left; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Codex-Mem Viewer</h1>
    <span id="status" class="meta">Loading</span>
  </header>
  <main>
    <section>
      <form id="search-form">
        <input id="query" name="query" placeholder="Search memory" autocomplete="off">
        <button type="submit">Search</button>
      </form>
      <p class="meta" id="result-count"></p>
      <div class="list" id="results"></div>
    </section>
    <aside>
      <h2>Memory Stream</h2>
      <div id="stream"></div>
    </aside>
  </main>
  <script>
    const results = document.querySelector("#results");
    const stream = document.querySelector("#stream");
    const status = document.querySelector("#status");
    const count = document.querySelector("#result-count");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      })[char]);
    }

    async function loadSearch(query = "") {
      const params = new URLSearchParams({ query, limit: "20" });
      const response = await fetch(`/memory/search?${params}`);
      const body = await response.json();
      count.textContent = `${body.results.length} results`;
      results.innerHTML = body.results.map(({ entry, score, reason }) => `
        <article class="row">
          <div class="type">${escapeHtml(entry.type)}</div>
          <div>
            <div class="title">${escapeHtml(entry.title)}</div>
            <div class="text">${escapeHtml(entry.context || entry.resolution || reason)}</div>
          </div>
          <div class="score">${Number(score).toFixed(2)}</div>
        </article>
      `).join("") || "<p class='meta'>No memory entries found.</p>";
    }

    async function loadStream() {
      const response = await fetch("/memory/history?limit=20");
      const body = await response.json();
      stream.innerHTML = body.map((event) => `
        <div class="event">
          <strong>${escapeHtml(event.action)} &middot; ${escapeHtml(event.snapshot.title)}</strong>
          <span class="text">${escapeHtml(event.timestamp)}</span>
        </div>
      `).join("") || "<p class='meta'>No history yet.</p>";
    }

    document.querySelector("#search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      loadSearch(new FormData(event.currentTarget).get("query"));
    });

    Promise.all([loadSearch(), loadStream()])
      .then(() => { status.textContent = "Ready"; })
      .catch((error) => {
        status.textContent = "Error";
        results.innerHTML = `<p class="meta">${escapeHtml(error.message)}</p>`;
      });
  </script>
</body>
</html>
        """.strip()
    )


@router.get("/team/search", response_model=SearchResponse)
def query_team_memory(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "normal",
    tags: list[str] = Query(default=[]),
) -> SearchResponse:
    settings = get_settings()
    if settings.team_backend != "local":
        raise HTTPException(status_code=501, detail=f"Unsupported team memory backend: {settings.team_backend}")
    results = get_store().search(
        query=query,
        limit=limit or SEARCH_PROFILE_LIMITS[profile],
        project="team",
        tags=tags,
    )
    return SearchResponse(results=results)


@router.get("/shared/{namespace}/search", response_model=SearchResponse)
def query_shared_namespace(
    namespace: str,
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "normal",
    tags: list[str] = Query(default=[]),
) -> SearchResponse:
    project = shared_namespace_project(namespace)
    results = get_store().search(
        query=query,
        limit=limit or SEARCH_PROFILE_LIMITS[profile],
        project=project,
        include_global=False,
        tags=tags,
    )
    return SearchResponse(results=results)


def shared_namespace_project(namespace: str) -> str:
    normalized = namespace.strip().lower().replace("\\", "-").replace("/", "-")
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in normalized).strip("-_")
    if not normalized:
        raise HTTPException(status_code=400, detail="Shared namespace must contain letters or numbers.")
    return f"shared:{normalized}"


@router.get("/health/diagnostics")
def health_diagnostics() -> dict:
    settings = get_settings()
    store = get_store()
    components = [
        {
            "name": "api",
            "status": "ok",
            "detail": "FastAPI router is responding.",
        },
        {
            "name": "db",
            "status": "ok" if store.db_path.exists() and store.metadata().get("schema_version") else "warning",
            "detail": str(store.db_path),
        },
        _json_file_component("mcp", settings.repo_root / "plugins" / "codex-mem" / ".mcp.json", "mcpServers"),
        _json_file_component("hooks", settings.repo_root / "plugins" / "codex-mem" / "hooks.json", "hooks"),
        _json_file_component(
            "plugin",
            settings.repo_root / "plugins" / "codex-mem" / ".codex-plugin" / "plugin.json",
            "name",
        ),
    ]
    overall = "ok" if all(component["status"] == "ok" for component in components) else "warning"
    return {"status": overall, "components": components, "config": settings.diagnostics()}


def _json_file_component(name: str, path, required_key: str) -> dict:
    if not path.exists():
        return {"name": name, "status": "missing", "detail": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"name": name, "status": "error", "detail": f"{path}: {error}"}
    if required_key not in payload:
        return {"name": name, "status": "warning", "detail": f"{path}: missing '{required_key}'"}
    return {"name": name, "status": "ok", "detail": str(path)}


@router.get("/smart/repeated-errors", response_model=RepeatedErrorResponse)
def repeated_errors(
    project: str | None = None,
    min_count: int = Query(default=2, ge=2, le=20),
    limit: int = Query(default=10, ge=1, le=50),
) -> RepeatedErrorResponse:
    return RepeatedErrorResponse(
        repeated_errors=get_store().repeated_errors(project=project, min_count=min_count, limit=limit)
    )


@router.get("/smart/anti-patterns", response_model=AntiPatternResponse)
def anti_patterns(
    project: str | None = None,
    min_count: int = Query(default=2, ge=2, le=20),
    limit: int = Query(default=10, ge=1, le=50),
) -> AntiPatternResponse:
    return AntiPatternResponse(
        anti_patterns=get_store().anti_patterns(project=project, min_count=min_count, limit=limit)
    )


@router.get("/smart/reused-solutions", response_model=ReusedSolutionResponse)
def reused_solutions(
    project: str | None = None,
    min_uses: int = Query(default=2, ge=1, le=100),
    limit: int = Query(default=10, ge=1, le=50),
) -> ReusedSolutionResponse:
    return ReusedSolutionResponse(
        reused_solutions=get_store().reused_solutions(project=project, min_uses=min_uses, limit=limit)
    )


@router.post("/smart/promote-best-practices", response_model=PromotedBestPracticeResponse)
def promote_best_practices(
    project: str | None = None,
    min_uses: int = Query(default=3, ge=1, le=100),
    min_confidence: float = Query(default=0.7, ge=0.0, le=1.0),
    limit: int = Query(default=10, ge=1, le=50),
) -> PromotedBestPracticeResponse:
    return PromotedBestPracticeResponse(
        promoted=get_store().promote_best_practices(
            project=project,
            min_uses=min_uses,
            min_confidence=min_confidence,
            limit=limit,
        )
    )


@router.post("/smart/summary", response_model=SummaryMemoryResponse)
def generate_summary_memory(
    query: str = "",
    project: str | None = None,
    limit: int = Query(default=5, ge=1, le=25),
) -> SummaryMemoryResponse:
    return SummaryMemoryResponse(
        summary=get_store().generate_summary_memory(query=query, project=project, limit=limit)
    )


@router.post("/smart/archive-low-value", response_model=ArchiveResponse)
def archive_low_value_memories(
    max_confidence: float = Query(default=0.4, ge=0.0, le=1.0),
    unused_days: int = Query(default=30, ge=0, le=3650),
    limit: int = Query(default=50, ge=1, le=500),
) -> ArchiveResponse:
    return ArchiveResponse(
        archived=get_store().archive_low_value_memories(
            max_confidence=max_confidence,
            unused_days=unused_days,
            limit=limit,
        )
    )


@router.post("/smart/consolidate", response_model=ConsolidationResponse)
def consolidate_memory(
    query: str = "",
    project: str | None = None,
) -> ConsolidationResponse:
    promoted, summary, archived = get_store().consolidate_memory(query=query, project=project)
    return ConsolidationResponse(promoted=promoted, summary=summary, archived=archived)


@router.post("/smart/link-related", response_model=MemoryLinkResponse)
def link_related_entries(project: str | None = None) -> MemoryLinkResponse:
    return MemoryLinkResponse(links=get_store().link_related_entries(project=project))


@router.post("/smart/recalculate-confidence", response_model=ConfidenceRecalculationResponse)
def recalculate_confidence(
    project: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> ConfidenceRecalculationResponse:
    return ConfidenceRecalculationResponse(
        updated=get_store().recalculate_confidence(project=project, limit=limit)
    )


@router.post("/sync/repo", response_model=RepoSyncResponse)
def sync_selected_to_repo() -> RepoSyncResponse:
    settings = get_settings()
    if not settings.sync_enabled:
        raise HTTPException(status_code=403, detail="Repo sync is disabled. Set sync.enabled or CODEX_MEM_SYNC_ENABLED=true to opt in.")
    synced, path = get_store().sync_selected_to_repo()
    return RepoSyncResponse(synced=synced, path=str(path))


def _resolve_markdown_import_path(store: MemoryStore, raw_path: str | None) -> Path:
    repo_root = store.codex_dir.parent.resolve()
    codex_dir = store.codex_dir.resolve()
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
    else:
        candidate = codex_dir / "MEMORY.md"

    resolved = candidate.resolve()
    allowed_roots = [repo_root, codex_dir]
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Markdown import path is outside the allowed repository boundary.")
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="Markdown import file does not exist.")
    if resolved.is_dir():
        raise HTTPException(status_code=400, detail="Markdown import path must be a file, not a directory.")
    if resolved.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Markdown import only accepts .md files.")
    if resolved.stat().st_size > MARKDOWN_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Markdown import file exceeds the {MARKDOWN_IMPORT_MAX_BYTES} byte limit.",
        )
    return resolved


@router.post("/import/markdown", response_model=MarkdownImportResponse)
def import_markdown_memory(payload: MarkdownImportRequest) -> MarkdownImportResponse:
    store = get_store()
    path = _resolve_markdown_import_path(store, payload.path)
    imported = store.import_markdown(path)
    return MarkdownImportResponse(imported=imported, path=str(path))


@router.get("/history", response_model=list[MemoryHistoryEntry])
def memory_history(
    memory_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[MemoryHistoryEntry]:
    return get_store().history(memory_id=memory_id, limit=limit)


@router.get("/audit", response_model=list[MemoryAuditEntry])
def memory_audit(
    memory_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[MemoryAuditEntry]:
    return get_store().audit_log(memory_id=memory_id, limit=limit)


@router.post("/{memory_id}/promote-global", response_model=MemoryEntry)
def promote_memory_to_global(memory_id: str) -> MemoryEntry:
    promoted = get_store().promote_to_global(memory_id)
    if not promoted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return promoted


@router.get("/{memory_id}", response_model=MemoryEntry)
def get_memory(memory_id: str) -> MemoryEntry:
    entry = get_store().get(memory_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return entry


@router.delete("/{memory_id}")
def delete_memory(memory_id: str) -> dict[str, bool]:
    deleted = get_store().delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"deleted": True}
