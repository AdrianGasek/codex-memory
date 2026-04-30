from functools import lru_cache
import json
from pathlib import Path
import os


class Settings:
    def __init__(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        config_path = repo_root / ".codex" / "mem.config.json"
        config = self._load_config(config_path)
        data_dir = Path(os.getenv("CODEX_MEM_DATA_DIR", repo_root / "data"))
        db_path = Path(os.getenv("CODEX_MEM_DB_PATH", data_dir / "db" / "codex-mem.sqlite3"))

        self.repo_root = repo_root
        self.data_dir = data_dir
        self.db_path = db_path
        self.codex_dir = repo_root / ".codex"
        self.config_path = config_path
        self.config = config
        self.default_project = os.getenv("CODEX_MEM_PROJECT", str(config.get("project") or repo_root.name))
        self.inject_limit = int(os.getenv("CODEX_MEM_INJECT_LIMIT", str(config.get("inject_limit") or 5)))
        self.token_budget = int(os.getenv("CODEX_MEM_TOKEN_BUDGET", str(config.get("token_budget") or 1200)))
        self.vector_backend = os.getenv("CODEX_MEM_VECTOR_BACKEND", str(config.get("vector_backend") or "local"))
        embeddings = config.get("embeddings") if isinstance(config.get("embeddings"), dict) else {}
        summarization = config.get("summarization") if isinstance(config.get("summarization"), dict) else {}
        debug = config.get("debug") if isinstance(config.get("debug"), dict) else {}
        self.embedding_provider = os.getenv("CODEX_MEM_EMBEDDING_PROVIDER", str(embeddings.get("provider") or "local"))
        self.embedding_model = os.getenv("CODEX_MEM_EMBEDDING_MODEL", str(embeddings.get("model") or "local-hash"))
        self.summarization_provider = os.getenv(
            "CODEX_MEM_SUMMARIZATION_PROVIDER",
            str(summarization.get("provider") or "local"),
        )
        self.summarization_model = os.getenv(
            "CODEX_MEM_SUMMARIZATION_MODEL",
            str(summarization.get("model") or "extractive"),
        )
        self.debug_verbose = os.getenv("CODEX_MEM_DEBUG_VERBOSE", str(debug.get("verbose", False))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.chroma_url = os.getenv("CODEX_MEM_CHROMA_URL", "http://127.0.0.1:8000")
        self.pgvector_dsn = os.getenv("CODEX_MEM_PGVECTOR_DSN", "")

    def _load_config(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
