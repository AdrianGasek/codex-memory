import json

from app.core.settings import Settings


def test_settings_loads_first_class_config():
    settings = Settings()

    assert settings.config_path.name == "mem.config.json"
    assert settings.config["project"] == "codex-brain"
    assert settings.inject_limit == 5
    assert settings.token_budget == 1200
    assert settings.embedding_provider == "local"
    assert settings.embedding_model == "local-hash"
    assert settings.summarization_provider == "local"
    assert settings.summarization_model == "extractive"
    assert settings.debug_verbose is False
    assert settings.sync_enabled is False
    assert settings.sync_scope == "local"
    assert settings.db_encryption_enabled is False
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
                "debug": {"verbose": "sometimes"},
                "unknown": True,
            }
        ),
        encoding="utf-8",
    )

    settings = Settings(repo_root=tmp_path)

    assert settings.default_project == tmp_path.name
    assert settings.inject_limit == 5
    assert settings.token_budget == 1200
    assert settings.debug_verbose is False
    diagnostics = settings.diagnostics()
    assert diagnostics["config_path"].endswith(".codex\\mem.config.json") or diagnostics["config_path"].endswith(
        ".codex/mem.config.json"
    )
    assert "Config key 'project' must be a string; using" in " ".join(diagnostics["diagnostics"])
    assert "Unknown config key 'unknown' will be ignored." in diagnostics["diagnostics"]
