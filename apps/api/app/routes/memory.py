from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from app.core.models import (
    AntiPatternResponse,
    ArchiveResponse,
    CompactIndexResponse,
    ConfidenceRecalculationResponse,
    ConsolidationResponse,
    CompactMemoryResult,
    InjectPreviewResponse,
    InjectResponse,
    InjectionTrace,
    MarkdownImportRequest,
    MarkdownImportResponse,
    MemoryCreate,
    MemoryAuditEntry,
    MemoryEntry,
    MemoryHistoryEntry,
    MemoryLinkResponse,
    MemoryExplanationResponse,
    MemoryStatsResponse,
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
from app.storage.vector import VectorBackendUnavailable, create_vector_store

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
            chroma_collection=settings.chroma_collection,
            chroma_timeout_seconds=settings.chroma_timeout_seconds,
            pgvector_dsn=settings.pgvector_dsn,
            allow_local_fallback=settings.vector_allow_local_fallback,
        ),
        encryption_key=settings.db_encryption_key if settings.db_encryption_enabled else None,
    )


@router.post("", response_model=MemoryEntry)
def store_memory(payload: MemoryCreate) -> MemoryEntry:
    validate_team_write(payload.project)
    validate_shared_write(payload.project)
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
        validate_team_read_project(project)
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


@router.get("/inject-preview", response_model=InjectPreviewResponse)
def inject_preview(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=20),
    profile: RetrievalProfile = "normal",
    token_budget: int | None = Query(default=None, ge=100, le=8000),
) -> InjectPreviewResponse:
    settings = get_settings()
    profile_limit = INJECT_PROFILE_LIMITS[profile] or settings.inject_limit
    return get_store().preview_injection(
        query=query,
        limit=limit or profile_limit,
        token_budget=token_budget or settings.token_budget,
    )


@router.get("/debug/injection", response_model=InjectionTrace | None)
def latest_injection_trace() -> InjectionTrace | None:
    return get_store().latest_injection_trace()


@router.get("/explain/{memory_id}", response_model=MemoryExplanationResponse)
def explain_memory(memory_id: str) -> MemoryExplanationResponse:
    explanation = get_store().explain_memory(memory_id)
    if not explanation:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return explanation


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


@router.get("/stats", response_model=MemoryStatsResponse)
def memory_stats(
    project: str | None = None,
    since: str | None = None,
    impact: bool = False,
) -> MemoryStatsResponse:
    try:
        return get_store().stats(project=project, since=since, include_impact=impact)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid stats filter: {error}") from error


@router.get("/config/diagnostics")
def config_diagnostics() -> dict:
    return get_settings().diagnostics()


@router.get("/viewer", response_class=HTMLResponse)
def local_memory_viewer() -> HTMLResponse:
    viewer_path = Path(__file__).resolve().parents[1] / "static" / "viewer.html"
    return HTMLResponse(viewer_path.read_text(encoding="utf-8"))


@router.get("/viewer/assets/{asset_name}")
def local_memory_viewer_asset(asset_name: str) -> Response:
    allowed_assets = {"viewer.css": "text/css", "viewer.js": "application/javascript"}
    media_type = allowed_assets.get(asset_name)
    if not media_type:
        raise HTTPException(status_code=404, detail="Viewer asset not found")
    asset_path = Path(__file__).resolve().parents[1] / "static" / asset_name
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Viewer asset not found")
    return Response(asset_path.read_text(encoding="utf-8"), media_type=media_type)


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
    require_team_role(settings.team_role, {"reader", "writer", "admin"})
    results = get_store().search(
        query=query,
        limit=limit or SEARCH_PROFILE_LIMITS[profile],
        project=team_namespace_project(settings.team_id),
        include_global=False,
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


@router.get("/shared/{namespace}/index", response_model=CompactIndexResponse)
def compact_shared_namespace_index(
    namespace: str,
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=50),
    profile: RetrievalProfile = "short",
    tags: list[str] = Query(default=[]),
) -> CompactIndexResponse:
    project = shared_namespace_project(namespace)
    results = get_store().search(
        query=query,
        limit=limit or SEARCH_PROFILE_LIMITS[profile],
        project=project,
        include_global=False,
        tags=tags,
    )
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


@router.get("/shared/namespaces")
def list_shared_namespaces() -> dict[str, list[str]]:
    return {"namespaces": get_store().shared_namespaces()}


def shared_namespace_project(namespace: str) -> str:
    normalized = namespace.strip().lower().replace("\\", "-").replace("/", "-")
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in normalized).strip("-_")
    if not normalized:
        raise HTTPException(status_code=400, detail="Shared namespace must contain letters or numbers.")
    return f"shared:{normalized}"


def team_namespace_project(team_id: str) -> str:
    normalized = team_id.strip().lower().replace("\\", "-").replace("/", "-")
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in normalized).strip("-_")
    if not normalized:
        raise HTTPException(status_code=400, detail="Team id must contain letters or numbers.")
    return f"team:{normalized}"


def require_team_role(role: str, allowed: set[str]) -> None:
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Team role '{role}' is not allowed for this operation.")


def validate_team_write(project: str | None) -> None:
    if not project or not project.startswith("team:"):
        return
    settings = get_settings()
    if not settings.team_write_enabled:
        raise HTTPException(
            status_code=403,
            detail="Team memory writes are disabled. Set team.write_enabled or CODEX_MEM_TEAM_WRITE_ENABLED=true.",
        )
    expected_project = team_namespace_project(settings.team_id)
    if project != expected_project:
        raise HTTPException(status_code=403, detail="Team memory write target does not match configured team id.")
    require_team_role(settings.team_role, {"writer", "admin"})


def validate_team_read_project(project: str | None) -> None:
    if not project or not project.startswith("team:"):
        return
    settings = get_settings()
    expected_project = team_namespace_project(settings.team_id)
    if project != expected_project:
        raise HTTPException(status_code=403, detail="Team memory read target does not match configured team id.")
    require_team_role(settings.team_role, {"reader", "writer", "admin"})


def validate_shared_write(project: str | None) -> None:
    if not project or not project.startswith("shared:"):
        return
    settings = get_settings()
    if not settings.shared_write_enabled:
        raise HTTPException(
            status_code=403,
            detail="Shared memory writes are disabled. Set shared.write_enabled or CODEX_MEM_SHARED_WRITE_ENABLED=true.",
        )


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
        _schema_component(store),
        _vector_component(settings, store),
        _team_component(settings),
        _encryption_component(settings),
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


def _schema_component(store: MemoryStore) -> dict:
    version = store.metadata().get("schema_version")
    if version:
        return {"name": "schema", "status": "ok", "detail": f"schema_version={version}"}
    return {"name": "schema", "status": "error", "detail": "Missing schema version metadata."}


def _vector_component(settings, store: MemoryStore) -> dict:
    if settings.vector_backend == "local":
        return {"name": "vector", "status": "ok", "detail": "local vector backend active"}
    try:
        store.vector_store.search([0.0], limit=1, project=settings.default_project)
    except VectorBackendUnavailable as error:
        return {"name": "vector", "status": "error", "detail": str(error)}
    except Exception as error:
        return {"name": "vector", "status": "error", "detail": f"Vector backend check failed: {error}"}
    return {"name": "vector", "status": "ok", "detail": f"{settings.vector_backend} backend reachable"}


def _team_component(settings) -> dict:
    if settings.team_backend != "local":
        return {"name": "team", "status": "error", "detail": f"Unsupported team backend: {settings.team_backend}"}
    if settings.team_role not in {"reader", "writer", "admin"}:
        return {"name": "team", "status": "error", "detail": f"Invalid team role: {settings.team_role}"}
    return {"name": "team", "status": "ok", "detail": f"local team namespace team:{settings.team_id}"}


def _encryption_component(settings) -> dict:
    if not settings.db_encryption_enabled:
        return {"name": "encryption", "status": "warning", "detail": "DB field encryption is disabled."}
    if not settings.db_encryption_key:
        return {"name": "encryption", "status": "error", "detail": "DB encryption is enabled but key is missing."}
    return {"name": "encryption", "status": "ok", "detail": "DB field encryption is enabled."}


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
    settings = get_settings()
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
        if not settings.migration_allow_external_paths:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Markdown import path is outside the allowed repository boundary. "
                    "Set migration.allow_external_paths or CODEX_MEM_MIGRATION_ALLOW_EXTERNAL_PATHS=true to opt in."
                ),
            )
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
    try:
        imported = store.import_markdown(path)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid Markdown import: {error}") from error
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
