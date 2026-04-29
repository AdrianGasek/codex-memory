from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
from uuid import uuid4

from app.core.models import (
    InjectionTrace,
    InjectionTraceEntry,
    MemoryCreate,
    MemoryEntry,
    MemoryHistoryEntry,
    SearchResult,
    new_entry,
)
from app.core.ranking import rank_memory

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
]


class MemoryStore:
    def __init__(self, db_path: Path, codex_dir: Path, default_project: str) -> None:
        self.db_path = db_path
        self.codex_dir = codex_dir
        self.default_project = default_project
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.codex_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
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
                    content_hash TEXT NOT NULL UNIQUE
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
            self._ensure_column(conn, "importance", "REAL NOT NULL DEFAULT 0.5")
            self._ensure_column(conn, "pinned", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "file_paths", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "retrieved_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "injected_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "last_used_timestamp", "TEXT")
            self._ensure_column(conn, "status", "TEXT NOT NULL DEFAULT 'active'")
            self._ensure_column(conn, "conflict_ids", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "superseded_by", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_history_memory_id ON memory_history(memory_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_history_timestamp ON memory_history(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_injection_traces_timestamp ON injection_traces(timestamp)")

    def _ensure_column(self, conn: sqlite3.Connection, name: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if name not in columns:
            conn.execute(f"ALTER TABLE memories ADD COLUMN {name} {definition}")

    def ensure_memory_files(self) -> None:
        defaults = {
            "MEMORY.md": "# MEMORY\n\nCodex-Mem exports validated memory entries here from SQLite.\n",
            "HISTORY.json": "[]\n",
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
                    last_used_timestamp, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.type.value,
                    entry.title,
                    entry.context,
                    entry.resolution,
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
                ),
            )
            self._record_history(conn, entry, "create")

        self.export_markdown()
        self.export_history()
        return entry

    def search(
        self,
        query: str = "",
        limit: int = 10,
        memory_type: str | None = None,
        project: str | None = None,
        tags: Iterable[str] | None = None,
        path: str | None = None,
        track_usage: bool = True,
    ) -> list[SearchResult]:
        where = []
        params: list[str | int] = []
        if memory_type:
            where.append("type = ?")
            params.append(memory_type)
        if project:
            where.append("project = ?")
            params.append(project)
        where.append("status = ?")
        params.append("active")

        sql = "SELECT * FROM memories"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(limit * 8, limit))

        requested_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        requested_path = self._normalize_path(path or "")
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
            if query.strip() and not ranked.matched:
                continue
            results.append(SearchResult(entry=entry, score=ranked.score, reason=ranked.reason))

        results.sort(key=lambda item: (item.score, item.entry.timestamp), reverse=True)
        selected = results[:limit]
        if track_usage:
            self._record_usage(selected, retrieved_delta=1, injected_delta=0)
        return selected

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if not existing:
                return False
            self._record_history(conn, self._from_row(existing), "delete")
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            deleted = cursor.rowcount > 0
        if deleted:
            self.export_markdown()
            self.export_history()
        return deleted

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

    def inject_context(self, query: str, limit: int, token_budget: int) -> tuple[str, list[SearchResult], InjectionTrace]:
        results = self.search(query=query, limit=limit)
        if not results:
            trace = self._record_injection_trace(query, limit, token_budget, [], 0)
            return "", [], trace

        lines = ["# Relevant Codex-Mem Context", ""]
        budget_chars = max(token_budget * 4, 400)
        injected_results = []
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
                break
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

    def _from_row(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            type=row["type"],
            title=row["title"],
            context=row["context"],
            resolution=row["resolution"],
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
            snapshot=MemoryEntry(**json.loads(row["snapshot"])),
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
            entries=[InjectionTraceEntry(**entry) for entry in json.loads(row["entries"])],
            timestamp=row["timestamp"],
        )

    def _redact(self, entry: MemoryEntry) -> MemoryEntry:
        data = entry.model_dump()
        for field in ("title", "context", "resolution"):
            value = data[field]
            for pattern in SECRET_PATTERNS:
                value = pattern.sub("[REDACTED]", value)
            data[field] = value
        return MemoryEntry(**data)

    def _hashable(self, entry: MemoryEntry) -> str:
        normalized = {
            "type": entry.type.value,
            "title": entry.title.strip().lower(),
            "context": entry.context.strip().lower(),
            "resolution": entry.resolution.strip().lower(),
            "file_paths": entry.file_paths,
            "project": entry.project,
        }
        return json.dumps(normalized, sort_keys=True)

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
            if self._conflict_key(row["title"]) == entry_key
            and self._scopes_overlap(json.loads(row["file_paths"]), entry.file_paths)
        ]

    def _normalize_path(self, path: str) -> str:
        return path.strip().replace("\\", "/").strip("/").lower()

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
                json.dumps(entry.model_dump(mode="json"), sort_keys=True),
                entry.source,
                entry.project,
                changed_at,
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
            query=query,
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
                    reason=result.reason,
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
                    json.dumps([entry.model_dump(mode="json") for entry in trace.entries], sort_keys=True),
                    trace.timestamp,
                ),
            )
        return trace
