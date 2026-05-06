from __future__ import annotations

import base64
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import json
import os
import re
import sqlite3
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.models import (
    AntiPattern,
    InjectionTrace,
    InjectionTraceEntry,
    MemoryAuditEntry,
    MemoryCreate,
    MemoryEntry,
    MemoryHistoryEntry,
    MemoryLink,
    MemoryUpdate,
    RepeatedError,
    ReusedSolution,
    SearchDebugResult,
    SearchResult,
    new_entry,
)
from app.core.ranking import rank_memory
from app.storage.vector import LocalVectorStore, VectorRecord, VectorStore

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"(?<![\d.])(?:\+?\d[\d ()-]{7,}\d)(?![\d.])"),
]
SCHEMA_VERSION = "1"


class MemoryStore:
    def __init__(
        self,
        db_path: Path,
        codex_dir: Path,
        default_project: str,
        vector_store: VectorStore | None = None,
        encryption_key: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.codex_dir = codex_dir
        self.default_project = default_project
        self.vector_store = vector_store or LocalVectorStore()
        self.encryption_key = encryption_key
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.codex_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        if hasattr(self.vector_store, "ensure_schema"):
            self.vector_store.ensure_schema()
        self.ensure_memory_files()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    context TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    file_paths TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL,
                    source TEXT NOT NULL,
                    project TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    conflict_ids TEXT NOT NULL DEFAULT '[]',
                    superseded_by TEXT,
                    retrieved_count INTEGER NOT NULL DEFAULT 0,
                    injected_count INTEGER NOT NULL DEFAULT 0,
                    last_used_timestamp TEXT,
                    content_hash TEXT NOT NULL UNIQUE,
                    embedding TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_history (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    snapshot TEXT NOT NULL,
                    source TEXT NOT NULL,
                    project TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    UNIQUE(memory_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS injection_traces (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    requested_limit INTEGER NOT NULL,
                    token_budget INTEGER NOT NULL,
                    injected_count INTEGER NOT NULL,
                    candidate_count INTEGER NOT NULL,
                    entries TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_links (
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (from_id, to_id, relation)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_audit (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    project TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO memory_metadata (key, value) VALUES (?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )
            self._ensure_column(conn, "importance", "REAL NOT NULL DEFAULT 0.5")
            self._ensure_column(conn, "pinned", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "file_paths", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "retrieved_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "injected_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "last_used_timestamp", "TEXT")
            self._ensure_column(conn, "status", "TEXT NOT NULL DEFAULT 'active'")
            self._ensure_column(conn, "conflict_ids", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "superseded_by", "TEXT")
            self._ensure_column(conn, "embedding", "TEXT NOT NULL DEFAULT '[]'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_history_memory_id ON memory_history(memory_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_history_timestamp ON memory_history(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_injection_traces_timestamp ON injection_traces(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_links_from ON memory_links(from_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_links_to ON memory_links(to_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_timestamp ON memory_audit(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_audit_memory_id ON memory_audit(memory_id)")

    def _ensure_column(self, conn: sqlite3.Connection, name: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")

    def ensure_memory_files(self) -> None:
        defaults = {
            "MEMORY.md": "# MEMORY\n\nCodex-Mem exports validated memory entries here from SQLite.\n",
            "HISTORY.json": "[]\n",
            "AUDIT.json": "[]\n",
            "SOUL.md": "# SOUL\n\nProject-level memory principles and agent preferences.\n",
            "CONTEXT.md": "# CONTEXT\n\nCurrent working context for Codex-Mem sessions.\n",
        }
        for filename, content in defaults.items():
            path = self.codex_dir / filename
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def store(self, payload: MemoryCreate) -> MemoryEntry:
        entry = new_entry(payload, self.default_project)
        entry = self._redact(entry)
        content_hash = self._hashable(entry)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM memories WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if existing:
                return self._from_row(existing)

            conflicts = self._find_conflicts(conn, entry)
            if conflicts:
                conflict_ids = [row["id"] for row in conflicts]
                entry = entry.model_copy(
                    update={
                        "conflict_ids": conflict_ids,
                    }
                )
                for conflict in conflicts:
                    existing_entry = self._from_row(conflict)
                    updated_conflict_ids = sorted(set(existing_entry.conflict_ids + [entry.id]))
                    superseded_entry = existing_entry.model_copy(
                        update={
                            "status": "superseded",
                            "conflict_ids": updated_conflict_ids,
                            "superseded_by": entry.id,
                        }
                    )
                    conn.execute(
                        """
                        UPDATE memories
                        SET status = ?, conflict_ids = ?, superseded_by = ?
                        WHERE id = ?
                        """,
                        (
                            superseded_entry.status,
                            json.dumps(superseded_entry.conflict_ids),
                            superseded_entry.superseded_by,
                            superseded_entry.id,
                        ),
                    )
                    self._record_history(conn, superseded_entry, "supersede")

            conn.execute(
                """
                INSERT INTO memories (
                    id, type, title, context, resolution, confidence, importance,
                    pinned, file_paths, tags, source, project, timestamp, status,
                    conflict_ids, superseded_by, retrieved_count, injected_count,
                    last_used_timestamp, content_hash, embedding
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.type.value,
                    self._protect_text(entry.title),
                    self._protect_text(entry.context),
                    self._protect_text(entry.resolution),
                    entry.confidence,
                    entry.importance,
                    int(entry.pinned),
                    json.dumps(entry.file_paths),
                    json.dumps(entry.tags),
                    entry.source,
                    entry.project,
                    entry.timestamp,
                    entry.status,
                    json.dumps(entry.conflict_ids),
                    entry.superseded_by,
                    entry.retrieved_count,
                    entry.injected_count,
                    entry.last_used_timestamp,
                    content_hash,
                    json.dumps(self._embedding_for_entry(entry)),
                ),
            )
            self.vector_store.upsert(self._vector_record_for_entry(entry))
            self._record_history(conn, entry, "create")
            if entry.project and (entry.project.startswith("team:") or entry.project.startswith("shared:")):
                self._record_audit(conn, entry, "create")

        self.export_markdown()
        self.export_history()
        return entry

    def search(
        self,
        query: str = "",
        limit: int = 10,
        memory_type: str | None = None,
        project: str | None = None,
        include_global: bool = True,
        tags: Iterable[str] | None = None,
        path: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        track_usage: bool = True,
    ) -> list[SearchResult]:
        project = project or self.default_project
        where = []
        params: list[str | int] = []
        if memory_type:
            where.append("type = ?")
            params.append(memory_type)
        if project:
            if include_global and project != "global":
                where.append("(project = ? OR project = ?)")
                params.extend([project, "global"])
            else:
                where.append("project = ?")
                params.append(project)
        if created_after:
            where.append("timestamp >= ?")
            params.append(self._normalize_timestamp_filter(created_after))
        if created_before:
            where.append("timestamp <= ?")
            params.append(self._normalize_timestamp_filter(created_before))
        where.append("status = ?")
        params.append("active")

        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(limit * 8, limit))

        requested_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        requested_path = self._normalize_path(path or "")
        query_embedding = self.vector_store.embed(query) if query.strip() else []
        backend_scores = self._backend_similarity_scores(query_embedding, limit=max(limit * 8, limit), project=project)
        results: list[SearchResult] = []

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        for row in rows:
            entry = self._from_row(row)
            if requested_tags and not requested_tags.intersection(entry.tags):
                continue
            if requested_path and not self._path_matches(entry.file_paths, requested_path):
                continue
            ranked = rank_memory(entry, query)
            backend_semantic_score = backend_scores.get(entry.id)
            semantic_score = (
                backend_semantic_score
                if backend_semantic_score is not None
                else self._semantic_score(row, entry, query_embedding)
            )
            if query.strip() and not ranked.matched and semantic_score < 0.25:
                continue
            score = ranked.score + (semantic_score * 2.0)
            reason = ranked.reason
            if backend_semantic_score is not None and semantic_score >= 0.25:
                reason = f"{reason}; external vector backend similarity"
            elif semantic_score >= 0.25:
                reason = f"{reason}; semantic embedding similarity"
            results.append(SearchResult(entry=entry, score=round(score, 6), reason=reason))

        results.sort(key=lambda item: (item.score, item.entry.timestamp), reverse=True)
        selected = results[:limit]
        if track_usage:
            self._record_usage(selected, retrieved_delta=1, injected_delta=0)
        return selected

    def search_debug(
        self,
        query: str = "",
        limit: int = 10,
        memory_type: str | None = None,
        project: str | None = None,
        tags: Iterable[str] | None = None,
        path: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> list[SearchDebugResult]:
        project = project or self.default_project
        where = []
        params: list[str | int] = []
        if memory_type:
            where.append("type = ?")
            params.append(memory_type)
        if project:
            if project != "global":
                where.append("(project = ? OR project = ?)")
                params.extend([project, "global"])
            else:
                where.append("project = ?")
                params.append(project)
        if created_after:
            where.append("timestamp >= ?")
            params.append(self._normalize_timestamp_filter(created_after))
        if created_before:
            where.append("timestamp <= ?")
            params.append(self._normalize_timestamp_filter(created_before))
        where.append("status = ?")
        params.append("active")

        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(limit * 8, limit))

        requested_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        requested_path = self._normalize_path(path or "")
        query_embedding = self.vector_store.embed(query) if query.strip() else []
        debug_results: list[SearchDebugResult] = []

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        for row in rows:
            entry = self._from_row(row)
            if requested_tags and not requested_tags.intersection(entry.tags):
                continue
            if requested_path and not self._path_matches(entry.file_paths, requested_path):
                continue
            ranked = rank_memory(entry, query)
            semantic_score = self._semantic_score(row, entry, query_embedding)
            if query.strip() and not ranked.matched and semantic_score < 0.25:
                continue
            components = dict(ranked.components)
            components["semantic"] = round(semantic_score * 2.0, 6)
            score = round(sum(components.values()), 6)
            reason = ranked.reason
            if semantic_score >= 0.25:
                reason = f"{reason}; semantic embedding similarity"
            debug_results.append(
                SearchDebugResult(
                    entry=entry,
                    score=score,
                    matched=ranked.matched or semantic_score >= 0.25,
                    reason=reason,
                    components=components,
                )
            )

        debug_results.sort(key=lambda item: (item.score, item.entry.timestamp), reverse=True)
        return debug_results[:limit]

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not existing:
                return False
            entry = self._from_row(existing)
            self._record_history(conn, entry, "delete")
            self._record_audit(conn, entry, "delete")
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            self.vector_store.delete(memory_id)
            self.export_markdown()
            self.export_history()
            self.export_audit()
        return deleted

    def get(self, memory_id: str) -> MemoryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ? AND status = 'active'",
                (memory_id,),
            ).fetchone()
        if not row:
            return None
        return self._from_row(row)

    def update(self, memory_id: str, payload: MemoryUpdate) -> MemoryEntry | None:
        updates = payload.model_dump(exclude_unset=True)
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not existing:
                return None

            current = self._from_row(existing)
            data = current.model_dump()
            data.update({key: value for key, value in updates.items() if value is not None})
            if "project" in updates and updates["project"] is None:
                data["project"] = current.project
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
            updated = self._redact(MemoryEntry(**data))
            content_hash = self._hashable(updated)

            duplicate = conn.execute(
                "SELECT id FROM memories WHERE content_hash = ? AND id != ?",
                (content_hash, memory_id),
            ).fetchone()
            if duplicate:
                raise ValueError(f"Updated memory would duplicate {duplicate['id']}")

            conn.execute(
                """
                UPDATE memories
                SET type = ?, title = ?, context = ?, resolution = ?, confidence = ?,
                    importance = ?, pinned = ?, file_paths = ?, tags = ?, source = ?,
                    project = ?, timestamp = ?, content_hash = ?, embedding = ?
                WHERE id = ?
                """,
                (
                    updated.type.value,
                    self._protect_text(updated.title),
                    self._protect_text(updated.context),
                    self._protect_text(updated.resolution),
                    updated.confidence,
                    updated.importance,
                    int(updated.pinned),
                    json.dumps(updated.file_paths),
                    json.dumps(updated.tags),
                    updated.source,
                    updated.project,
                    updated.timestamp,
                    content_hash,
                    json.dumps(self._embedding_for_entry(updated)),
                    updated.id,
                ),
            )
            self.vector_store.upsert(self._vector_record_for_entry(updated))
            self._record_history(conn, updated, "update")
            self._record_audit(conn, updated, "update")

        self.export_markdown()
        self.export_history()
        self.export_audit()
        return updated

    def promote_to_global(self, memory_id: str) -> MemoryEntry | None:
        entry = self.get(memory_id)
        if not entry:
            return None
        if entry.project == "global":
            return entry
        tags = sorted(set(entry.tags + ["cross-project", "global"]))
        return self.store(
            MemoryCreate(
                type=entry.type,
                title=entry.title,
                context=entry.context,
                resolution=entry.resolution,
                confidence=entry.confidence,
                importance=entry.importance,
                pinned=entry.pinned,
                file_paths=entry.file_paths,
                tags=tags,
                source="cross-project",
                project="global",
            )
        )

    def history(self, memory_id: str | None = None, limit: int = 100) -> list[MemoryHistoryEntry]:
        params: list[str | int] = []
        sql = "SELECT * FROM memory_history"
        if memory_id:
            sql += " WHERE memory_id = ?"
            params.append(memory_id)
        sql += " ORDER BY timestamp DESC, version DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._history_from_row(row) for row in rows]

    def audit_log(self, memory_id: str | None = None, limit: int = 100) -> list[MemoryAuditEntry]:
        params: list[str | int] = []
        sql = "SELECT * FROM memory_audit"
        if memory_id:
            sql += " WHERE memory_id = ?"
            params.append(memory_id)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._audit_from_row(row) for row in rows]

    def inject_context(self, query: str, limit: int, token_budget: int) -> tuple[str, list[SearchResult], InjectionTrace]:
        results = self.search(query=query, limit=limit)
        if not results:
            trace = self._record_injection_trace(query, limit, token_budget, [], 0)
            return "", [], trace

        lines = ["# Relevant Codex-Mem Context", ""]
        budget_chars = max(token_budget * 4, 400)
        injected_results = []
        summarized = False
        for result in results:
            entry = result.entry
            block = [
                f"- [{entry.type.value}] {entry.title} ({entry.id}, score={result.score:.2f})",
                f"  Context: {entry.context}" if entry.context else "",
                f"  Resolution: {entry.resolution}" if entry.resolution else "",
                f"  Files: {', '.join(entry.file_paths)}" if entry.file_paths else "",
                f"  Tags: {', '.join(entry.tags)}" if entry.tags else "",
            ]
            candidate = "\n".join(part for part in block if part)
            if len("\n".join(lines)) + len(candidate) > budget_chars:
                summary = self._summary_for_result(result)
                if not summarized and len("\n".join(lines)) + len("\n# Summarized Memory\n") <= budget_chars:
                    lines.extend(["", "# Summarized Memory"])
                    summarized = True
                if len("\n".join(lines)) + len(summary) > budget_chars:
                    break
                lines.append(summary)
                injected_results.append(result)
                continue
            lines.append(candidate)
            injected_results.append(result)
        self._record_usage(injected_results, retrieved_delta=0, injected_delta=1)
        trace = self._record_injection_trace(query, limit, token_budget, injected_results, len(results))
        return "\n".join(lines).strip(), results, trace

    def latest_injection_trace(self) -> InjectionTrace | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM injection_traces
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return self._trace_from_row(row)

    def metadata(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM memory_metadata ORDER BY key").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def repeated_errors(
        self,
        project: str | None = None,
        min_count: int = 2,
        limit: int = 10,
    ) -> list[RepeatedError]:
        sql = "SELECT * FROM memories WHERE type = ?"
        params: list[str] = ["bug"]
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY timestamp DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        groups: dict[str, list[MemoryEntry]] = {}
        for row in rows:
            entry = self._from_row(row)
            groups.setdefault(self._conflict_key(entry.title), []).append(entry)

        repeated = []
        for key, entries in groups.items():
            if len(entries) < min_count:
                continue
            entries.sort(key=lambda entry: entry.timestamp, reverse=True)
            repeated.append(
                RepeatedError(
                    key=key,
                    title=entries[0].title,
                    count=len(entries),
                    memory_ids=[entry.id for entry in entries],
                    last_seen_timestamp=entries[0].timestamp,
                )
            )

        repeated.sort(key=lambda item: (item.count, item.last_seen_timestamp), reverse=True)
        return repeated[:limit]

    def anti_patterns(
        self,
        project: str | None = None,
        min_count: int = 2,
        limit: int = 10,
    ) -> list[AntiPattern]:
        return [
            AntiPattern(
                key=error.key,
                title=f"Anti-pattern: {error.title}",
                evidence_count=error.count,
                memory_ids=error.memory_ids,
                recommendation="Avoid repeating this failure mode; prefer a validated solution or add a guard before retrying.",
            )
            for error in self.repeated_errors(project=project, min_count=min_count, limit=limit)
        ]

    def reused_solutions(
        self,
        project: str | None = None,
        min_uses: int = 2,
        limit: int = 10,
    ) -> list[ReusedSolution]:
        sql = """
            SELECT * FROM memories
            WHERE type = ? AND status = 'active'
              AND (retrieved_count + injected_count) >= ?
        """
        params: list[str | int] = ["solution", min_uses]
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY (retrieved_count + injected_count) DESC, last_used_timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        solutions = []
        for row in rows:
            entry = self._from_row(row)
            solutions.append(
                ReusedSolution(
                    id=entry.id,
                    title=entry.title,
                    retrieved_count=entry.retrieved_count,
                    injected_count=entry.injected_count,
                    total_uses=entry.retrieved_count + entry.injected_count,
                    last_used_timestamp=entry.last_used_timestamp,
                )
            )
        return solutions

    def promote_best_practices(
        self,
        project: str | None = None,
        min_uses: int = 3,
        min_confidence: float = 0.7,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        promoted = []
        for candidate in self.reused_solutions(project=project, min_uses=min_uses, limit=limit):
            entry = self.get(candidate.id)
            if not entry or entry.confidence < min_confidence:
                continue
            promoted.append(
                self.store(
                    MemoryCreate(
                        type="pattern",
                        title=f"Best practice: {entry.title}",
                        context=entry.context,
                        resolution=entry.resolution,
                        confidence=max(entry.confidence, 0.85),
                        importance=max(entry.importance, 0.8),
                        file_paths=entry.file_paths,
                        tags=sorted(set(entry.tags + ["best-practice", "promoted"])),
                        source="smart-promotion",
                        project=entry.project,
                    )
                )
            )
        return promoted

    def generate_summary_memory(
        self,
        query: str = "",
        project: str | None = None,
        limit: int = 5,
    ) -> MemoryEntry | None:
        results = self.search(
            query=query,
            limit=limit,
            project=project,
            track_usage=False,
        )
        if not results:
            return None

        lines = []
        for result in results:
            entry = result.entry
            detail = entry.resolution or entry.context
            compact = " ".join(detail.split())
            if len(compact) > 180:
                compact = compact[:177].rstrip() + "..."
            lines.append(f"- [{entry.type.value}] {entry.title}: {compact}")

        title_subject = query.strip() or (project or self.default_project)
        return self.store(
            MemoryCreate(
                type="fact",
                title=f"Summary: {title_subject}"[:120],
                context="\n".join(lines),
                resolution="Generated as a compact summary of high-ranking memory entries.",
                confidence=0.75,
                importance=0.7,
                tags=["summary", "generated"],
                source="smart-summary",
                project=project,
            )
        )

    def archive_low_value_memories(
        self,
        max_confidence: float = 0.4,
        unused_days: int = 30,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=unused_days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE status = 'active'
                  AND pinned = 0
                  AND confidence <= ?
                  AND retrieved_count = 0
                  AND injected_count = 0
                  AND timestamp <= ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (max_confidence, cutoff.isoformat(), limit),
            ).fetchall()

            archived = []
            for row in rows:
                entry = self._from_row(row).model_copy(update={"status": "archived"})
                conn.execute("UPDATE memories SET status = ? WHERE id = ?", ("archived", entry.id))
                self._record_history(conn, entry, "archive")
                archived.append(entry)

        if archived:
            self.export_markdown()
            self.export_history()
        return archived

    def consolidate_memory(
        self,
        query: str = "",
        project: str | None = None,
    ) -> tuple[list[MemoryEntry], MemoryEntry | None, list[MemoryEntry]]:
        promoted = self.promote_best_practices(project=project, min_uses=3, limit=10)
        summary = self.generate_summary_memory(query=query, project=project, limit=5)
        archived = self.archive_low_value_memories(max_confidence=0.4, unused_days=30, limit=50)
        return promoted, summary, archived

    def link_related_entries(self, project: str | None = None) -> list[MemoryLink]:
        where = "WHERE status = 'active'"
        params: list[str] = []
        if project:
            where += " AND project = ?"
            params.append(project)
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM memories {where}", params).fetchall()
            entries = [self._from_row(row) for row in rows]
            bugs = [entry for entry in entries if entry.type.value == "bug"]
            solutions = [entry for entry in entries if entry.type.value == "solution"]
            patterns = [entry for entry in entries if entry.type.value == "pattern"]
            links: list[MemoryLink] = []
            for bug in bugs:
                for solution in solutions:
                    if self._entries_related(bug, solution):
                        links.append(MemoryLink(from_id=bug.id, to_id=solution.id, relation="bug_solution"))
            for solution in solutions:
                for pattern in patterns:
                    if self._entries_related(solution, pattern) or pattern.title.lower().endswith(solution.title.lower()):
                        links.append(MemoryLink(from_id=solution.id, to_id=pattern.id, relation="solution_pattern"))
            now = datetime.now(timezone.utc).isoformat()
            conn.executemany(
                """
                INSERT OR IGNORE INTO memory_links (from_id, to_id, relation, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                [(link.from_id, link.to_id, link.relation, now) for link in links],
            )
            rows = conn.execute("SELECT from_id, to_id, relation FROM memory_links").fetchall()
        return [MemoryLink(from_id=row["from_id"], to_id=row["to_id"], relation=row["relation"]) for row in rows]

    def _entries_related(self, left: MemoryEntry, right: MemoryEntry) -> bool:
        left_tags = set(left.tags)
        right_tags = set(right.tags)
        if left_tags and left_tags.intersection(right_tags):
            return True
        left_tokens = set(self._conflict_key(left.title).split())
        right_tokens = set(self._conflict_key(right.title).split())
        return len(left_tokens.intersection(right_tokens)) >= 2

    def recalculate_confidence(self, project: str | None = None, limit: int = 100) -> list[MemoryEntry]:
        sql = "SELECT * FROM memories WHERE status = 'active'"
        params: list[str | int] = []
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        updated = []
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                entry = self._from_row(row)
                usage = entry.retrieved_count + (entry.injected_count * 2)
                usage_boost = min(0.2, usage * 0.02)
                validation_boost = 0.1 if "validated" in entry.tags else 0.0
                recalculated = min(1.0, max(entry.confidence, entry.confidence + usage_boost + validation_boost))
                if recalculated == entry.confidence:
                    continue
                changed = entry.model_copy(update={"confidence": round(recalculated, 4)})
                conn.execute("UPDATE memories SET confidence = ? WHERE id = ?", (changed.confidence, changed.id))
                self._record_history(conn, changed, "update")
                updated.append(changed)
        if updated:
            self.export_markdown()
            self.export_history()
        return updated

    def _summary_for_result(self, result: SearchResult) -> str:
        entry = result.entry
        source = entry.resolution or entry.context
        summary = " ".join(source.split())
        if len(summary) > 140:
            summary = summary[:137].rstrip() + "..."
        return f"- [{entry.type.value}] {entry.title}: {summary} ({entry.id}, score={result.score:.2f})"

    def export_markdown(self) -> None:
        results = self.search(limit=500, track_usage=False)
        memory_path = self.codex_dir / "MEMORY.md"
        index_path = self.codex_dir / "INDEX.json"
        lines = ["# MEMORY", "", "Generated from SQLite. Edit through Codex-Mem commands when possible.", ""]
        index = []

        for result in results:
            entry = result.entry
            lines.extend(
                [
                    f"## {entry.title}",
                    "",
                    f"- id: `{entry.id}`",
                    f"- type: `{entry.type.value}`",
                    f"- confidence: `{entry.confidence:.2f}`",
                    f"- importance: `{entry.importance:.2f}`",
                    f"- pinned: `{entry.pinned}`",
                    f"- file_paths: `{', '.join(entry.file_paths)}`" if entry.file_paths else "- file_paths: ``",
                    f"- source: `{entry.source}`",
                    f"- project: `{entry.project}`",
                    f"- timestamp: `{entry.timestamp}`",
                    f"- status: `{entry.status}`",
                    f"- superseded_by: `{entry.superseded_by or ''}`",
                    f"- conflict_ids: `{', '.join(entry.conflict_ids)}`" if entry.conflict_ids else "- conflict_ids: ``",
                    f"- retrieved_count: `{entry.retrieved_count}`",
                    f"- injected_count: `{entry.injected_count}`",
                    f"- last_used_timestamp: `{entry.last_used_timestamp or ''}`",
                    f"- tags: `{', '.join(entry.tags)}`" if entry.tags else "- tags: ``",
                    "",
                ]
            )
            if entry.context:
                lines.extend(["### Context", "", entry.context, ""])
            if entry.resolution:
                lines.extend(["### Resolution", "", entry.resolution, ""])
            index.append(entry.model_dump(mode="json"))

        memory_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def export_history(self) -> None:
        history_path = self.codex_dir / "HISTORY.json"
        entries = [entry.model_dump(mode="json") for entry in self.history(limit=1000)]
        history_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def export_audit(self) -> None:
        audit_path = self.codex_dir / "AUDIT.json"
        entries = [entry.model_dump(mode="json") for entry in self.audit_log(limit=1000)]
        audit_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def import_markdown(self, markdown_path: Path | None = None) -> list[MemoryEntry]:
        path = markdown_path or (self.codex_dir / "MEMORY.md")
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        blocks = re.split(r"(?m)^## ", text)
        imported = []
        for block in blocks[1:]:
            lines = block.splitlines()
            if not lines:
                continue
            title = lines[0].strip()
            metadata: dict[str, str] = {}
            context_lines: list[str] = []
            resolution_lines: list[str] = []
            section: str | None = None
            for line in lines[1:]:
                if line == "### Context":
                    section = "context"
                    continue
                if line == "### Resolution":
                    section = "resolution"
                    continue
                if line.startswith("- ") and section is None:
                    key, _, value = line[2:].partition(":")
                    metadata[key.strip()] = value.strip().strip("`")
                    continue
                if section == "context" and line.strip():
                    context_lines.append(line)
                if section == "resolution" and line.strip():
                    resolution_lines.append(line)
            memory_type = metadata.get("type", "fact")
            if memory_type not in {"fact", "decision", "bug", "solution", "pattern"}:
                raise ValueError(f"entry '{title}' has unsupported type '{memory_type}'.")
            try:
                confidence = float(metadata.get("confidence") or 0.75)
                importance = float(metadata.get("importance") or 0.5)
            except ValueError as error:
                raise ValueError(f"entry '{title}' has non-numeric confidence or importance.") from error
            if not 0 <= confidence <= 1 or not 0 <= importance <= 1:
                raise ValueError(f"entry '{title}' confidence and importance must be between 0 and 1.")
            imported.append(
                self.store(
                    MemoryCreate(
                        type=memory_type,
                        title=title,
                        context="\n".join(context_lines).strip(),
                        resolution="\n".join(resolution_lines).strip(),
                        confidence=confidence,
                        importance=importance,
                        pinned=metadata.get("pinned", "False") == "True",
                        file_paths=[path.strip() for path in metadata.get("file_paths", "").split(",") if path.strip()],
                        tags=[tag.strip() for tag in metadata.get("tags", "").split(",") if tag.strip()],
                        source=metadata.get("source") or "markdown-import",
                        project=metadata.get("project") or None,
                    )
                )
            )
        return imported

    def sync_selected_to_repo(self) -> tuple[list[MemoryEntry], Path]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE status = 'active' AND (pinned = 1 OR tags LIKE ?)
                ORDER BY timestamp DESC
                """,
                ('%"repo-sync"%',),
            ).fetchall()
        entries = [self._from_row(row) for row in rows]
        with self._connect() as conn:
            for entry in entries:
                self._record_audit(conn, entry, "sync")
        path = self.codex_dir / "SYNCED_MEMORY.json"
        path.write_text(
            json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2),
            encoding="utf-8",
        )
        return entries, path

    def shared_namespaces(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM memories WHERE project LIKE 'shared:%' ORDER BY project"
            ).fetchall()
        return [row["project"].split(":", 1)[1] for row in rows if row["project"]]

    def _from_row(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            type=row["type"],
            title=self._unprotect_text(row["title"]),
            context=self._unprotect_text(row["context"]),
            resolution=self._unprotect_text(row["resolution"]),
            confidence=row["confidence"],
            importance=row["importance"],
            pinned=bool(row["pinned"]),
            file_paths=json.loads(row["file_paths"]),
            tags=json.loads(row["tags"]),
            source=row["source"],
            project=row["project"],
            timestamp=row["timestamp"],
            status=row["status"],
            conflict_ids=json.loads(row["conflict_ids"]),
            superseded_by=row["superseded_by"],
            retrieved_count=row["retrieved_count"],
            injected_count=row["injected_count"],
            last_used_timestamp=row["last_used_timestamp"],
        )

    def _history_from_row(self, row: sqlite3.Row) -> MemoryHistoryEntry:
        return MemoryHistoryEntry(
            id=row["id"],
            memory_id=row["memory_id"],
            version=row["version"],
            action=row["action"],
            snapshot=MemoryEntry(**json.loads(self._unprotect_text(row["snapshot"]))),
            source=row["source"],
            project=row["project"],
            timestamp=row["timestamp"],
        )

    def _audit_from_row(self, row: sqlite3.Row) -> MemoryAuditEntry:
        return MemoryAuditEntry(
            id=row["id"],
            memory_id=row["memory_id"],
            action=row["action"],
            title=self._unprotect_text(row["title"]),
            source=row["source"],
            project=row["project"],
            timestamp=row["timestamp"],
        )

    def _trace_from_row(self, row: sqlite3.Row) -> InjectionTrace:
        return InjectionTrace(
            id=row["id"],
            query=row["query"],
            requested_limit=row["requested_limit"],
            token_budget=row["token_budget"],
            injected_count=row["injected_count"],
            candidate_count=row["candidate_count"],
            entries=[InjectionTraceEntry(**entry) for entry in json.loads(self._unprotect_text(row["entries"]))],
            timestamp=row["timestamp"],
        )

    def _protect_text(self, value: str) -> str:
        if not self.encryption_key or not value:
            return value
        salt = os.urandom(16)
        nonce = os.urandom(12)
        plain = value.encode("utf-8")
        cipher = AESGCM(self._derive_encryption_key(salt)).encrypt(nonce, plain, None)
        return "enc:v2:" + ":".join(
            [
                base64.urlsafe_b64encode(salt).decode("ascii"),
                base64.urlsafe_b64encode(nonce).decode("ascii"),
                base64.urlsafe_b64encode(cipher).decode("ascii"),
            ]
        )

    def _unprotect_text(self, value: str) -> str:
        if not self.encryption_key or not isinstance(value, str) or not value.startswith("enc:v2:"):
            return value
        try:
            _prefix, _version, salt_text, nonce_text, cipher_text = value.split(":", 4)
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            nonce = base64.urlsafe_b64decode(nonce_text.encode("ascii"))
            cipher = base64.urlsafe_b64decode(cipher_text.encode("ascii"))
            plain = AESGCM(self._derive_encryption_key(salt)).decrypt(nonce, cipher, None)
            return plain.decode("utf-8")
        except (InvalidTag, ValueError, OSError, UnicodeDecodeError):
            return "[DECRYPTION FAILED]"

    def _derive_encryption_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200_000,
        )
        return kdf.derive(self.encryption_key.encode("utf-8"))

    def _redact(self, entry: MemoryEntry) -> MemoryEntry:
        data = entry.model_dump()
        for field in ("title", "context", "resolution"):
            data[field] = self._redact_text(data[field])
        return MemoryEntry(**data)

    def _redact_text(self, value: str) -> str:
        try:
            for pattern in SECRET_PATTERNS:
                value = pattern.sub("[REDACTED]", value)
        except Exception:
            return "[REDACTED]"
        return value

    def _hashable(self, entry: MemoryEntry) -> str:
        normalized = {
            "type": entry.type.value,
            "title": entry.title.strip().lower(),
            "context": entry.context.strip().lower(),
            "resolution": entry.resolution.strip().lower(),
            "file_paths": entry.file_paths,
            "project": entry.project,
        }
        return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode("utf-8")).hexdigest()

    def _conflict_key(self, value: str) -> str:
        return " ".join(normalized.strip(".,;!?()[]{}'\"`").lower() for normalized in value.split())

    def _find_conflicts(self, conn: sqlite3.Connection, entry: MemoryEntry) -> list[sqlite3.Row]:
        rows = conn.execute(
            """
            SELECT * FROM memories
            WHERE type = ? AND project = ? AND status = 'active'
            """,
            (entry.type.value, entry.project),
        ).fetchall()
        entry_key = self._conflict_key(entry.title)
        return [
            row
            for row in rows
            if self._conflict_key(self._unprotect_text(row["title"])) == entry_key
            and self._scopes_overlap(json.loads(row["file_paths"]), entry.file_paths)
        ]

    def _normalize_path(self, path: str) -> str:
        return path.strip().replace("\\", "/").strip("/").lower()

    def _normalize_timestamp_filter(self, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    def _embedding_for_entry(self, entry: MemoryEntry) -> list[float]:
        return self.vector_store.embed(
            " ".join(
                [
                    entry.title,
                    entry.context,
                    entry.resolution,
                    " ".join(entry.file_paths),
                    " ".join(entry.tags),
                    entry.type.value,
                    entry.source,
                ]
            )
        )

    def _vector_record_for_entry(self, entry: MemoryEntry) -> VectorRecord:
        return VectorRecord(
            memory_id=entry.id,
            embedding=self._embedding_for_entry(entry),
            document="\n".join([entry.title, entry.context, entry.resolution]).strip(),
            metadata={"project": entry.project or self.default_project, "type": entry.type.value},
        )

    def _backend_similarity_scores(
        self,
        query_embedding: list[float],
        *,
        limit: int,
        project: str | None,
    ) -> dict[str, float]:
        if not query_embedding:
            return {}
        return {
            result.memory_id: result.score
            for result in self.vector_store.search(query_embedding, limit=limit, project=project)
        }

    def _semantic_score(
        self,
        row: sqlite3.Row,
        entry: MemoryEntry,
        query_embedding: list[float],
    ) -> float:
        if not query_embedding:
            return 0.0
        try:
            entry_embedding = json.loads(row["embedding"])
        except (IndexError, KeyError, TypeError, json.JSONDecodeError):
            entry_embedding = []
        if not entry_embedding:
            entry_embedding = self._embedding_for_entry(entry)
        return self.vector_store.similarity(query_embedding, entry_embedding)

    def _path_matches(self, file_paths: list[str], requested_path: str) -> bool:
        normalized_paths = [self._normalize_path(path) for path in file_paths]
        for file_path in normalized_paths:
            if (
                file_path == requested_path
                or file_path.startswith(f"{requested_path}/")
                or requested_path.startswith(f"{file_path}/")
            ):
                return True
        return False

    def _scopes_overlap(self, existing_paths: list[str], new_paths: list[str]) -> bool:
        if not existing_paths or not new_paths:
            return True
        return any(self._path_matches(existing_paths, self._normalize_path(path)) for path in new_paths)

    def _record_usage(
        self,
        results: list[SearchResult],
        retrieved_delta: int,
        injected_delta: int,
    ) -> None:
        if not results:
            return

        used_at = datetime.now(timezone.utc).isoformat()
        ids = [result.entry.id for result in results]
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE memories
                SET retrieved_count = retrieved_count + ?,
                    injected_count = injected_count + ?,
                    last_used_timestamp = ?
                WHERE id = ?
                """,
                [(retrieved_delta, injected_delta, used_at, memory_id) for memory_id in ids],
            )

        for result in results:
            result.entry.retrieved_count += retrieved_delta
            result.entry.injected_count += injected_delta
            result.entry.last_used_timestamp = used_at

    def _record_history(
        self,
        conn: sqlite3.Connection,
        entry: MemoryEntry,
        action: str,
    ) -> None:
        version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM memory_history WHERE memory_id = ?",
            (entry.id,),
        ).fetchone()[0]
        changed_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO memory_history (
                id, memory_id, version, action, snapshot, source, project, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"hist_{uuid4().hex[:12]}",
                entry.id,
                version,
                action,
                self._protect_text(json.dumps(entry.model_dump(mode="json"), sort_keys=True)),
                entry.source,
                entry.project,
                changed_at,
            ),
        )

    def _record_audit(
        self,
        conn: sqlite3.Connection,
        entry: MemoryEntry,
        action: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO memory_audit (
                id, memory_id, action, title, source, project, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"audit_{uuid4().hex[:12]}",
                entry.id,
                action,
                self._protect_text(entry.title),
                entry.source,
                entry.project,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _record_injection_trace(
        self,
        query: str,
        requested_limit: int,
        token_budget: int,
        injected_results: list[SearchResult],
        candidate_count: int,
    ) -> InjectionTrace:
        trace = InjectionTrace(
            id=f"trace_{uuid4().hex[:12]}",
            query=self._redact_text(query),
            requested_limit=requested_limit,
            token_budget=token_budget,
            injected_count=len(injected_results),
            candidate_count=candidate_count,
            entries=[
                InjectionTraceEntry(
                    memory_id=result.entry.id,
                    title=result.entry.title,
                    type=result.entry.type,
                    score=result.score,
                    reason=self._redact_text(result.reason),
                )
                for result in injected_results
            ],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO injection_traces (
                    id, query, requested_limit, token_budget, injected_count,
                    candidate_count, entries, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.id,
                    trace.query,
                    trace.requested_limit,
                    trace.token_budget,
                    trace.injected_count,
                    trace.candidate_count,
                    self._protect_text(
                        json.dumps([entry.model_dump(mode="json") for entry in trace.entries], sort_keys=True)
                    ),
                    trace.timestamp,
                ),
            )
        return trace
