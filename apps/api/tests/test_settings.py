import json

from app.core.settings import Settings


def test_settings_loads_first_class_config():
    settings = Settings()

    assert settings.config_path.name == "mem.config.json"
    assert settings.config["project"] == "codex-brain"
    assert settings.inject_limit == 5
    assert settings.token_budget == 1200
    assert settings.vector_allow_local_fallback is False
    assert settings.chroma_collection == "codex_mem"
    assert settings.chroma_timeout_seconds == 5
    assert settings.embedding_provider == "local"
    assert settings.embedding_model == "local-hash"
    assert settings.summarization_provider == "local"
    assert settings.summarization_model == "extractive"
    assert settings.debug_verbose is False
    assert settings.sync_enabled is False
    assert settings.sync_scope == "local"
    assert settings.shared_write_enabled is False
    assert settings.migration_allow_external_paths is False
    assert settings.db_encryption_enabled is False
    assert settings.team_id == "default"
    assert settings.team_role == "reader"
    assert settings.team_write_enabled is False
    assert settings.team_backend == "local"


def test_settings_validates_config_and_reports_diagnostics(tmp_path):
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "mem.config.json").write_text(
        json.dumps(
            {
                "project": 123,
                "inject_limit": 0,
                "token_budget": "bad",
                "vector": {
                    "allow_local_fallback": "sometimes",
                    "chroma_collection": 123,
                    "chroma_timeout_seconds": 0,
                },
                "debug": {"verbose": "sometimes"},
                "shared": {"write_enabled": "sometimes"},
                "migration": {"allow_external_paths": "sometimes"},
                "team": {"id": 123, "role": "owner", "backend": "remote"},
                "unknown": True,
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(repo_root=tmp_path)

    assert settings.default_project == tmp_path.name
    assert settings.inject_limit == 5
    assert settings.token_budget == 1200
    assert settings.vector_allow_local_fallback is False
    assert settings.chroma_collection == "codex_mem"
    assert settings.chroma_timeout_seconds == 5
    assert settings.debug_verbose is False
    assert settings.shared_write_enabled is False
    assert settings.migration_allow_external_paths is False
    assert settings.team_id == "default"
    assert settings.team_role == "owner"
    assert settings.team_backend == "remote"
    diagnostics = settings.diagnostics()
    assert diagnostics["config_path"].endswith(".codex\\mem.config.json") or diagnostics["config_path"].endswith(
        ".codex/mem.config.json"
    )
    assert "Config key 'project' must be a string; using" in " ".join(diagnostics["diagnostics"])
    assert "Config key 'allow_local_fallback' must be a boolean; using False." in diagnostics["diagnostics"]
    assert "Config key 'chroma_collection' must be a string; using 'codex_mem'." in diagnostics["diagnostics"]
    assert "Config key 'chroma_timeout_seconds' must be at least 1; using 5." in diagnostics["diagnostics"]
    assert "Config key 'write_enabled' must be a boolean; using False." in diagnostics["diagnostics"]
    assert "Config key 'allow_external_paths' must be a boolean; using False." in diagnostics["diagnostics"]
    assert "Config key 'id' must be a string; using 'default'." in diagnostics["diagnostics"]
    assert "Config key 'team.role' should be one of reader, writer, or admin; got 'owner'." in diagnostics[
        "diagnostics"
    ]
    assert "Config key 'team.backend' should be local; got 'remote'." in diagnostics["diagnostics"]
    assert "Unknown config key 'unknown' will be ignored." in diagnostics["diagnostics"]
