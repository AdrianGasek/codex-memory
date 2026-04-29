from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class MemoryType(str, Enum):
    fact = "fact"
    decision = "decision"
    bug = "bug"
    solution = "solution"
    pattern = "pattern"


class MemoryCreate(BaseModel):
    type: MemoryType
    title: str = Field(min_length=1, max_length=160)
    context: str = Field(default="", max_length=4000)
    resolution: str = Field(default="", max_length=4000)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    pinned: bool = False
    file_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="manual", max_length=120)
    project: str | None = Field(default=None, max_length=180)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = []
        for tag in tags:
            value = tag.strip().lower()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned

    @field_validator("file_paths")
    @classmethod
    def clean_file_paths(cls, file_paths: list[str]) -> list[str]:
        cleaned = []
        for path in file_paths:
            value = path.strip().replace("\\", "/").strip("/")
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned


class MemoryUpdate(BaseModel):
    type: MemoryType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    context: str | None = Field(default=None, max_length=4000)
    resolution: str | None = Field(default=None, max_length=4000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    pinned: bool | None = None
    file_paths: list[str] | None = None
    tags: list[str] | None = None
    source: str | None = Field(default=None, max_length=120)
    project: str | None = Field(default=None, max_length=180)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        return MemoryCreate.clean_tags(tags)

    @field_validator("file_paths")
    @classmethod
    def clean_file_paths(cls, file_paths: list[str] | None) -> list[str] | None:
        if file_paths is None:
            return None
        return MemoryCreate.clean_file_paths(file_paths)


class MemoryEntry(MemoryCreate):
    id: str
    timestamp: str
    status: Literal["active", "superseded"] = "active"
    conflict_ids: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    retrieved_count: int = 0
    injected_count: int = 0
    last_used_timestamp: str | None = None


class MemoryHistoryEntry(BaseModel):
    id: str
    memory_id: str
    version: int
    action: Literal["create", "delete", "supersede", "update"]
    snapshot: MemoryEntry
    source: str
    project: str
    timestamp: str


def new_entry(payload: MemoryCreate, project: str) -> MemoryEntry:
    now = datetime.now(timezone.utc).isoformat()
    return MemoryEntry(
        id=f"mem_{uuid4().hex[:12]}",
        timestamp=now,
        retrieved_count=0,
        injected_count=0,
        last_used_timestamp=None,
        project=payload.project or project,
        **payload.model_dump(exclude={"project"}),
    )


class SearchResult(BaseModel):
    entry: MemoryEntry
    score: float
    reason: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult]


class CompactMemoryResult(BaseModel):
    id: str
    type: MemoryType
    title: str
    score: float
    reason: str = ""
    tags: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)


class CompactIndexResponse(BaseModel):
    results: list[CompactMemoryResult]


class InjectionTraceEntry(BaseModel):
    memory_id: str
    title: str
    type: MemoryType
    score: float
    reason: str


class InjectionTrace(BaseModel):
    id: str
    query: str
    requested_limit: int
    token_budget: int
    injected_count: int
    candidate_count: int
    entries: list[InjectionTraceEntry]
    timestamp: str


class InjectResponse(BaseModel):
    additional_context: str
    results: list[SearchResult]
    trace: InjectionTrace | None = None


class ErrorResponse(BaseModel):
    error: str
    details: dict[str, Any] = Field(default_factory=dict)
