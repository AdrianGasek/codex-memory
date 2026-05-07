from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol
from urllib import error, request

from app.core.embeddings import cosine_similarity, embed_text


@dataclass(frozen=True)
class VectorRecord:
    memory_id: str
    embedding: list[float]
    document: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class VectorSearchResult:
    memory_id: str
    score: float
    metadata: dict[str, str]


class VectorBackendUnavailable(RuntimeError):
    """Raised when a configured external vector backend cannot handle requests."""


class VectorStore(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return a normalized embedding vector for text."""

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        """Return similarity between two vectors in the 0..1 range."""

    def upsert(self, record: VectorRecord) -> None:
        """Store or replace an embedding record in the backend."""

    def delete(self, memory_id: str) -> None:
        """Remove an embedding record from the backend if it exists."""

    def search(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        """Return backend-ranked nearest neighbors for a query embedding."""


class ChromaClient(Protocol):
    def upsert(self, record: VectorRecord) -> None:
        """Store or replace a vector record."""

    def delete(self, memory_id: str) -> None:
        """Delete a vector record."""

    def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        """Query nearest vector records."""


class PgVectorClient(Protocol):
    def ensure_schema(self) -> None:
        """Create required pgvector extension and tables."""

    def upsert(self, record: VectorRecord) -> None:
        """Store or replace a vector record."""

    def delete(self, memory_id: str) -> None:
        """Delete a vector record."""

    def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        """Query nearest vector records."""


@dataclass(frozen=True)
class ChromaHttpClient:
    url: str
    collection: str = "codex_mem"
    timeout_seconds: int = 5

    def upsert(self, record: VectorRecord) -> None:
        self._post(
            "upsert",
            {
                "ids": [record.memory_id],
                "embeddings": [record.embedding],
                "documents": [record.document],
                "metadatas": [record.metadata],
            },
        )

    def delete(self, memory_id: str) -> None:
        self._post("delete", {"ids": [memory_id]})

    def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        where = {"project": project} if project else None
        payload = {"query_embeddings": [query_vector], "n_results": limit}
        if where:
            payload["where"] = where
        data = self._post("query", payload)
        ids = (data.get("ids") or [[]])[0]
        distances = (data.get("distances") or [[]])[0]
        metadatas = (data.get("metadatas") or [[]])[0]
        results = []
        for index, memory_id in enumerate(ids):
            distance = distances[index] if index < len(distances) else 1.0
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            results.append(VectorSearchResult(memory_id=str(memory_id), score=max(0.0, 1.0 - float(distance)), metadata=metadata))
        return results

    def _post(self, action: str, payload: dict) -> dict:
        endpoint = f"{self.url.rstrip('/')}/api/v1/collections/{self.collection}/{action}"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except (OSError, error.URLError, error.HTTPError) as exc:
            raise VectorBackendUnavailable(f"Chroma vector backend request failed: {exc}") from exc
        return json.loads(response_body) if response_body else {}


@dataclass(frozen=True)
class PgVectorSqlClient:
    dsn: str
    table: str = "codex_mem_vectors"

    def ensure_schema(self) -> None:
        self._execute("CREATE EXTENSION IF NOT EXISTS vector", ())
        self._execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table} (
                memory_id TEXT PRIMARY KEY,
                embedding vector,
                document TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                project TEXT
            )
            """,
            (),
        )
        self._execute(
            f"CREATE INDEX IF NOT EXISTS {self.table}_project_idx ON {self.table} (project)",
            (),
        )

    def upsert(self, record: VectorRecord) -> None:
        self._execute(
            f"""
            INSERT INTO {self.table} (memory_id, embedding, document, metadata, project)
            VALUES (%s, %s::vector, %s, %s::jsonb, %s)
            ON CONFLICT (memory_id) DO UPDATE
            SET embedding = EXCLUDED.embedding,
                document = EXCLUDED.document,
                metadata = EXCLUDED.metadata,
                project = EXCLUDED.project
            """,
            (
                record.memory_id,
                self._vector_literal(record.embedding),
                record.document,
                json.dumps(record.metadata),
                record.metadata.get("project"),
            ),
        )

    def delete(self, memory_id: str) -> None:
        self._execute(f"DELETE FROM {self.table} WHERE memory_id = %s", (memory_id,))

    def query(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        where = "WHERE project = %s" if project else ""
        vector = self._vector_literal(query_vector)
        params: tuple = (vector, project, vector, limit) if project else (vector, vector, limit)
        rows = self._fetchall(
            f"""
            SELECT memory_id, 1 - (embedding <=> %s::vector) AS score, metadata
            FROM {self.table}
            {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            params,
        )
        return [
            VectorSearchResult(memory_id=str(row[0]), score=float(row[1]), metadata=row[2] or {})
            for row in rows
        ]

    def _execute(self, sql: str, params: tuple) -> None:
        psycopg = self._psycopg()
        try:
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, params)
                conn.commit()
        except Exception as exc:
            raise VectorBackendUnavailable(f"pgvector backend schema/write failed: {exc}") from exc

    def _fetchall(self, sql: str, params: tuple) -> list:
        psycopg = self._psycopg()
        try:
            with psycopg.connect(self.dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchall()
        except Exception as exc:
            raise VectorBackendUnavailable(f"pgvector backend query failed: {exc}") from exc

    def _psycopg(self):
        if not self.dsn:
            raise VectorBackendUnavailable("pgvector backend requires CODEX_MEM_PGVECTOR_DSN.")
        try:
            import psycopg
        except ImportError as exc:
            raise VectorBackendUnavailable("pgvector backend requires the psycopg package.") from exc
        return psycopg

    def _vector_literal(self, values: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in values) + "]"


@dataclass(frozen=True)
class LocalVectorStore:
    """Offline vector adapter used when no external backend is configured."""

    def embed(self, text: str) -> list[float]:
        return embed_text(text)

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        return cosine_similarity(query_vector, entry_vector)

    def upsert(self, record: VectorRecord) -> None:
        return None

    def delete(self, memory_id: str) -> None:
        return None

    def search(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        return []


@dataclass(frozen=True)
class ChromaVectorStore:
    url: str
    collection: str = "codex_mem"
    timeout_seconds: int = 5
    client: ChromaClient | None = None

    def embed(self, text: str) -> list[float]:
        return embed_text(text)

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        return cosine_similarity(query_vector, entry_vector)

    def upsert(self, record: VectorRecord) -> None:
        self._client().upsert(record)

    def delete(self, memory_id: str) -> None:
        self._client().delete(memory_id)

    def search(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        return self._client().query(query_vector, limit=limit, project=project)

    def _client(self) -> ChromaClient:
        return self.client or ChromaHttpClient(
            url=self.url,
            collection=self.collection,
            timeout_seconds=self.timeout_seconds,
        )


@dataclass(frozen=True)
class PgVectorStore:
    dsn: str
    table: str = "codex_mem_vectors"
    client: PgVectorClient | None = None

    def ensure_schema(self) -> None:
        self._client().ensure_schema()

    def embed(self, text: str) -> list[float]:
        return embed_text(text)

    def similarity(self, query_vector: list[float], entry_vector: list[float]) -> float:
        return cosine_similarity(query_vector, entry_vector)

    def upsert(self, record: VectorRecord) -> None:
        self._client().upsert(record)

    def delete(self, memory_id: str) -> None:
        self._client().delete(memory_id)

    def search(self, query_vector: list[float], *, limit: int, project: str | None = None) -> list[VectorSearchResult]:
        return self._client().query(query_vector, limit=limit, project=project)

    def _client(self) -> PgVectorClient:
        return self.client or PgVectorSqlClient(dsn=self.dsn, table=self.table)


def create_vector_store(
    backend: str = "local",
    *,
    chroma_url: str = "http://127.0.0.1:8000",
    chroma_collection: str = "codex_mem",
    chroma_timeout_seconds: int = 5,
    pgvector_dsn: str = "",
    allow_local_fallback: bool = False,
) -> VectorStore:
    normalized = backend.strip().lower()
    if normalized in {"", "local", "sqlite"}:
        return LocalVectorStore()
    if allow_local_fallback:
        return LocalVectorStore()
    if normalized == "chroma":
        return ChromaVectorStore(
            url=chroma_url,
            collection=chroma_collection,
            timeout_seconds=chroma_timeout_seconds,
        )
    if normalized == "pgvector":
        return PgVectorStore(dsn=pgvector_dsn)
    raise ValueError(f"Unsupported vector backend: {backend}")
