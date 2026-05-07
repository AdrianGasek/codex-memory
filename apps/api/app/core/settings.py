from functools import lru_cache
import json
from pathlib import Path
import os


class Settings:
    def __init__(self, repo_root: Path | None = None) -> None:
        repo_root = repo_root or Path(__file__).resolve().parents[4]
        config_path = repo_root / ".codex" / "mem.config.json"
        self.config_diagnostics: list[str] = []
        config = self._load_config(config_path)
        storage = self._config_section(config, "storage")
        data_dir = self._config_path(
            repo_root,
            os.getenv("CODEX_MEM_DATA_DIR", self._config_str(storage, "data_dir", "data")),
        )
        db_path = self._config_path(
            repo_root,
            os.getenv("CODEX_MEM_DB_PATH", self._config_str(storage, "db_path", str(data_dir / "db" / "codex-mem.sqlite3"))),
        )

        self.repo_root = repo_root
        self.data_dir = data_dir
        self.db_path = db_path
        self.codex_dir = repo_root / ".codex"
        self.config_path = config_path
        self.config = config
        self.default_project = os.getenv("CODEX_MEM_PROJECT", self._config_str(config, "project", repo_root.name))
        self.inject_limit = self._config_int("CODEX_MEM_INJECT_LIMIT", config, "inject_limit", 5, minimum=1)
        self.token_budget = self._config_int("CODEX_MEM_TOKEN_BUDGET", config, "token_budget", 1200, minimum=100)
        self.vector_backend = os.getenv("CODEX_MEM_VECTOR_BACKEND", self._config_str(config, "vector_backend", "local"))
        vector = self._config_section(config, "vector")
        embeddings = self._config_section(config, "embeddings")
        summarization = self._config_section(config, "summarization")
        debug = self._config_section(config, "debug")
        sync = self._config_section(config, "sync")
        shared = self._config_section(config, "shared")
        team = self._config_section(config, "team")
        migration = self._config_section(config, "migration")
        self.embedding_provider = os.getenv("CODEX_MEM_EMBEDDING_PROVIDER", self._config_str(embeddings, "provider", "local"))
        self.embedding_model = os.getenv("CODEX_MEM_EMBEDDING_MODEL", self._config_str(embeddings, "model", "local-hash"))
        self.summarization_provider = os.getenv(
            "CODEX_MEM_SUMMARIZATION_PROVIDER",
            self._config_str(summarization, "provider", "local"),
        )
        self.summarization_model = os.getenv(
            "CODEX_MEM_SUMMARIZATION_MODEL",
            self._config_str(summarization, "model", "extractive"),
        )
        self.debug_verbose = self._config_bool("CODEX_MEM_DEBUG_VERBOSE", debug, "verbose", False)
        self.sync_enabled = self._config_bool("CODEX_MEM_SYNC_ENABLED", sync, "enabled", False)
        self.sync_scope = os.getenv("CODEX_MEM_SYNC_SCOPE", self._config_str(sync, "scope", "local"))
        self.shared_write_enabled = self._config_bool(
            "CODEX_MEM_SHARED_WRITE_ENABLED",
            shared,
            "write_enabled",
            False,
        )
        self.vector_allow_local_fallback = self._config_bool(
            "CODEX_MEM_VECTOR_ALLOW_LOCAL_FALLBACK",
            vector,
            "allow_local_fallback",
            False,
        )
        self.migration_allow_external_paths = self._config_bool(
            "CODEX_MEM_MIGRATION_ALLOW_EXTERNAL_PATHS",
            migration,
            "allow_external_paths",
            False,
        )
        self.team_id = os.getenv("CODEX_MEM_TEAM_ID", self._config_str(team, "id", "default"))
        self.team_role = os.getenv("CODEX_MEM_TEAM_ROLE", self._config_str(team, "role", "reader"))
        self.team_write_enabled = self._config_bool("CODEX_MEM_TEAM_WRITE_ENABLED", team, "write_enabled", False)
        self.team_backend = os.getenv("CODEX_MEM_TEAM_BACKEND", self._config_str(team, "backend", "local"))
        security = self._config_section(config, "security")
        self.db_encryption_enabled = self._config_bool(
            "CODEX_MEM_DB_ENCRYPTION_ENABLED",
            security,
            "db_encryption_enabled",
            False,
        )
        self.db_encryption_key = os.getenv("CODEX_MEM_DB_ENCRYPTION_KEY", "")
        if self.db_encryption_enabled and not self.db_encryption_key:
            self.config_diagnostics.append(
                "DB encryption is enabled but CODEX_MEM_DB_ENCRYPTION_KEY is empty; storage startup will fail."
            )
        self.chroma_url = os.getenv("CODEX_MEM_CHROMA_URL", "http://127.0.0.1:8000")
        self.chroma_collection = os.getenv("CODEX_MEM_CHROMA_COLLECTION", self._config_str(vector, "chroma_collection", "codex_mem"))
        self.chroma_timeout_seconds = self._config_int(
            "CODEX_MEM_CHROMA_TIMEOUT_SECONDS",
            vector,
            "chroma_timeout_seconds",
            5,
            minimum=1,
        )
        self.pgvector_dsn = os.getenv("CODEX_MEM_PGVECTOR_DSN", "")
        self._validate_config(config)

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(config, dict):
                return config
            self.config_diagnostics.append(f"{path} must contain a JSON object; using defaults.")
        except (OSError, json.JSONDecodeError):
            self.config_diagnostics.append(f"Could not read valid JSON from {path}; using defaults.")
        return {}

    def _config_section(self, config: dict, key: str) -> dict:
        value = config.get(key)
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        self.config_diagnostics.append(f"Config key '{key}' must be an object; ignoring it.")
        return {}

    def _config_str(self, config: dict, key: str, default: str) -> str:
        value = config.get(key)
        if value is None or value == "":
            return default
        if isinstance(value, str):
            return value
        self.config_diagnostics.append(f"Config key '{key}' must be a string; using '{default}'.")
        return default

    def _config_int(self, env_name: str, config: dict, key: str, default: int, minimum: int) -> int:
        raw_value = os.getenv(env_name, config.get(key, default))
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            self.config_diagnostics.append(f"Config key '{key}' must be an integer; using {default}.")
            return default
        if value < minimum:
            self.config_diagnostics.append(f"Config key '{key}' must be at least {minimum}; using {default}.")
            return default
        return value

    def _config_bool(self, env_name: str, config: dict, key: str, default: bool) -> bool:
        raw_value = os.getenv(env_name, config.get(key, default))
        if isinstance(raw_value, bool):
            return raw_value
        normalized = str(raw_value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        self.config_diagnostics.append(f"Config key '{key}' must be a boolean; using {default}.")
        return default

    def _validate_config(self, config: dict) -> None:
        allowed_top_level = {
            "project",
            "inject_limit",
            "token_budget",
            "vector_backend",
            "storage",
            "api",
            "vector",
            "embeddings",
            "summarization",
            "capture",
            "debug",
            "sync",
            "shared",
            "migration",
            "security",
            "team",
        }
        for key in sorted(set(config) - allowed_top_level):
            self.config_diagnostics.append(f"Unknown config key '{key}' will be ignored.")

        if self.vector_backend not in {"local", "chroma", "pgvector"}:
            self.config_diagnostics.append(
                f"Config key 'vector_backend' should be one of local, chroma, or pgvector; got '{self.vector_backend}'."
            )
        if self.team_backend not in {"local"}:
            self.config_diagnostics.append(
                f"Config key 'team.backend' should be local; got '{self.team_backend}'."
            )
        if self.team_role not in {"reader", "writer", "admin"}:
            self.config_diagnostics.append(
                f"Config key 'team.role' should be one of reader, writer, or admin; got '{self.team_role}'."
            )

    def diagnostics(self) -> dict:
        return {
            "config_path": str(self.config_path),
            "diagnostics": self.config_diagnostics,
            "debug_verbose": self.debug_verbose,
            "inject_limit": self.inject_limit,
            "token_budget": self.token_budget,
            "vector_backend": self.vector_backend,
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "vector_allow_local_fallback": self.vector_allow_local_fallback,
            "chroma_url": self.chroma_url,
            "chroma_collection": self.chroma_collection,
            "chroma_timeout_seconds": self.chroma_timeout_seconds,
            "sync_enabled": self.sync_enabled,
            "sync_scope": self.sync_scope,
            "shared_write_enabled": self.shared_write_enabled,
            "migration_allow_external_paths": self.migration_allow_external_paths,
            "db_encryption_enabled": self.db_encryption_enabled and bool(self.db_encryption_key),
            "team_backend": self.team_backend,
            "team_id": self.team_id,
            "team_role": self.team_role,
            "team_write_enabled": self.team_write_enabled,
        }

    def _config_path(self, repo_root: Path, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path
        return repo_root / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
