from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.embeddings import cosine_similarity, embed_text


class VectorStore(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding vector for text."""

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        """Return similarity between two vectors in the 0..1 range."""


@dataclass(frozen=True)
class LocalVectorStore:
    """Offline vector adapter used when no external backend is configured."""

    def embed(self, text: str) -> list[float]:
        return embed_text(text)

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        return cosine_similarity(query_vector, entry_vector)


@dataclass(frozen=True)
class ChromaVectorStore(LocalVectorStore):
    url: str


@dataclass(frozen=True)
class PgVectorStore(LocalVectorStore):
    dsn: str


def create_vector_store(
    backend: str = "local",
    *,
    chroma_url: str = "http://127.0.0.1:8000",
    pgvector_dsn: str = "",
) -> VectorStore:
    normalized = backend.strip().lower()
    if normalized in {"", "local", "sqlite"}:
        return LocalVectorStore()
    if normalized == "chroma":
        return ChromaVectorStore(url=chroma_url)
    if normalized == "pgvector":
        return PgVectorStore(dsn=pgvector_dsn)
    raise ValueError(f"Unsupported vector backend: {backend}")
