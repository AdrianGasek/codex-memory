from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from app.core.models import (
    InjectResponse,
    InjectionTrace,
    MemoryCreate,
    MemoryEntry,
    MemoryHistoryEntry,
    SearchResponse,
)
from app.core.settings import get_settings
from app.storage.sqlite import MemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])


@lru_cache
def get_store() -> MemoryStore:
    settings = get_settings()
    return MemoryStore(
        db_path=settings.db_path,
        codex_dir=settings.codex_dir,
        default_project=settings.default_project,
    )


@router.post("", response_model=MemoryEntry)
def store_memory(payload: MemoryCreate) -> MemoryEntry:
    return get_store().store(payload)


@router.get("/search", response_model=SearchResponse)
def query_memory(
    query: str = "",
    limit: int = Query(default=10, ge=1, le=50),
    type: str | None = None,
    project: str | None = None,
    path: str | None = None,
    tags: list[str] = Query(default=[]),
) -> SearchResponse:
    results = get_store().search(
        query=query,
        limit=limit,
        memory_type=type,
        project=project,
        tags=tags,
        path=path,
    )
    return SearchResponse(results=results)


@router.get("/inject", response_model=InjectResponse)
def inject_memory(
    query: str = "",
    limit: int | None = Query(default=None, ge=1, le=20),
    token_budget: int | None = Query(default=None, ge=100, le=8000),
) -> InjectResponse:
    settings = get_settings()
    additional_context, results, trace = get_store().inject_context(
        query=query,
        limit=limit or settings.inject_limit,
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


@router.delete("/{memory_id}")
def delete_memory(memory_id: str) -> dict[str, bool]:
    deleted = get_store().delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"deleted": True}
