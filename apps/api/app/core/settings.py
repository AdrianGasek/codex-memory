from functools import lru_cache
from pathlib import Path
import os


class Settings:
    def __init__(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        data_dir = Path(os.getenv("CODEX_MEM_DATA_DIR", repo_root / "data"))
        db_path = Path(os.getenv("CODEX_MEM_DB_PATH", data_dir / "db" / "codex-mem.sqlite3"))

        self.repo_root = repo_root
        self.data_dir = data_dir
        self.db_path = db_path
        self.codex_dir = repo_root / ".codex"
        self.default_project = os.getenv("CODEX_MEM_PROJECT", repo_root.name)
        self.inject_limit = int(os.getenv("CODEX_MEM_INJECT_LIMIT", "5"))
        self.token_budget = int(os.getenv("CODEX_MEM_TOKEN_BUDGET", "1200"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
