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
