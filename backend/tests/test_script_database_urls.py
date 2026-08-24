import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "scripts.execute_district_population_ingestion",
        "scripts.validate_evidence_resolver",
        "scripts.verify_luapula_population",
    ],
)
def test_async_scripts_normalize_render_style_database_url(monkeypatch, module_name: str):
    module = importlib.import_module(module_name)
    monkeypatch.setattr(
        module.settings,
        "DATABASE_URL",
        "postgresql://user:p%40ss@render-postgres.example/statflow?sslmode=require",
    )
    captured = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(module, "create_async_engine", fake_create_async_engine)
    module.create_script_engine()

    assert captured["url"] == (
        "postgresql+asyncpg://user:p%40ss@render-postgres.example/statflow?sslmode=require"
    )
