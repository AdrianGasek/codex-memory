from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.models import (
    AntiPatternResponse,
    ArchiveResponse,
    CompactIndexResponse,
    ConfidenceRecalculationResponse,
    ConsolidationResponse,
    CompactMemoryResult,
    InjectResponse,
    InjectionTrace,
    MemoryCreate,
    MemoryEntry,
    MemoryHistoryEntry,
    MemoryLinkResponse,
    MemoryUpdate,
    PromotedBestPracticeResponse,
    RepeatedErrorResponse,
    RepoSyncResponse,
    ReusedSolutionResponse,
    SearchResponse,
    SummaryMemoryResponse,
)
from app.core.settings import get_settings
from app.storage.sqlite import MemoryStore
from app.storage.vector import create_vector_store

router = APIRouter(prefix="/memory", tags=["memory"])

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
    return MemoryStore(
        db_path=settings.db_path,
        codex_dir=settings.codex_dir,
        default_project=settings.default_project,
        vector_store=create_vector_store(
            settings.vector_backend,
            chroma_url=settings.chroma_url,
            pgvector_dsn=settings.pgvector_dsn,
        ),
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


@router.get("/metadata")
def memory_metadata() -> dict[str, str]:
    return get_store().metadata()


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
    synced, path = get_store().sync_selected_to_repo()
    return RepoSyncResponse(synced=synced, path=str(path))


@router.get("/history", response_model=list[MemoryHistoryEntry])
def memory_history(
    memory_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[MemoryHistoryEntry]:
    return get_store().history(memory_id=memory_id, limit=limit)


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
