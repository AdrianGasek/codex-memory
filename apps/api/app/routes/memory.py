from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.models import (
    CompactIndexResponse,
    CompactMemoryResult,
    InjectResponse,
    InjectionTrace,
    MemoryCreate,
    MemoryEntry,
    MemoryHistoryEntry,
    MemoryUpdate,
    SearchResponse,
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
