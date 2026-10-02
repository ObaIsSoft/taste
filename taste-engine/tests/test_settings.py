from taste_engine.settings import PROJECT_ROOT, Settings


def test_defaults_resolve_inside_project():
    settings = Settings()
    assert settings.data_dir.is_relative_to(PROJECT_ROOT)
    assert settings.manifest_path.is_relative_to(PROJECT_ROOT)


def test_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA_DIR", str(tmp_path))
    assert Settings().data_dir == tmp_path
